"""
IncrementalOptimizer : re-optimise UNIQUEMENT la zone d'impact, avec stabilite.

Modele CP-SAT dedie, distinct de `CPSATSolver.solve_with_context` (decision D2 de
docs/CONTEXTE_ET_DECISIONS.md) : dans le LNS initial le contexte droit est
approximatif et purement informationnel — le parametre y est d'ailleurs ignore —
alors qu'ici il est exact et CONTRAIGNANT (la zone ne peut pas deborder sur le
planning futur non touche). Ce sont deux semantiques differentes, pas deux jeux de
parametres.

Objectif (cf. Sec. 2.5 du document d'architecture) :

    Minimiser  somme(w_j * T_j) sur les jobs de la zone
             + STABILITY_WEIGHT * somme |debut_nouveau(j) - debut_original(j)|

Le second terme combat la "nervosite du planning" : sans lui, CP-SAT peut proposer
un reagencement complet pour un gain marginal, et le chef d'atelier perd confiance
dans l'outil. C'est une contrainte MOLLE : elle oriente vers la solution la plus
proche de l'originale parmi les solutions quasi optimales, sans interdire de bouger
un job quand c'est vraiment necessaire.

La valeur absolue est linearisee de facon standard avec deux variables auxiliaires
par job (delta positif / delta negatif) — jamais un abs() dans le modele.
"""
import logging
import time

from ortools.sat.python import cp_model

from scheduling.models.job import Job, ProblemInstance
from scheduling.models.perturbation import PerturbationType
from scheduling.models.schedule import JobResult, Schedule, ScheduleEntry, SetupEntry
from scheduling.models.window import Window, WindowResult

logger = logging.getLogger(__name__)


def _occupation_start(entry) -> int:
    """Debut d'occupation reelle de la machine : le setup precede l'operation."""
    if entry.setup and entry.setup.duration > 0:
        return min(entry.start_time, entry.setup.start_time)
    return entry.start_time

# Poids par defaut du terme de stabilite. Faible : la stabilite departage les
# solutions quasi optimales, elle ne domine pas le retard pondere.
DEFAULT_STABILITY_WEIGHT = 0.1
# Timeout court : la zone est petite par construction (cf. Sec. 2.4).
DEFAULT_TIMEOUT_SECONDS = 12

# Les poids du projet sont des flottants ; le modele CP-SAT travaille en entiers.
# Meme facteur d'echelle que CPSATSolver, pour que les objectifs soient comparables.
WEIGHT_SCALE = 100


class IncrementalOptimizer:
    """Re-optimise la zone d'impact sous contraintes de frontiere exactes."""

    def __init__(
        self,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        stability_weight: float = DEFAULT_STABILITY_WEIGHT,
        num_search_workers: int = 4,
    ):
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds doit etre > 0, recu {timeout_seconds}")
        if stability_weight < 0:
            raise ValueError(f"stability_weight doit etre >= 0, recu {stability_weight}")
        self.timeout_seconds = timeout_seconds
        self.stability_weight = stability_weight
        self.num_search_workers = num_search_workers

    # ----------------------------------------------------------------------
    def optimize(self, zone, contexts, instance) -> WindowResult:
        """Re-optimise la zone d'impact.

        Args:
            zone: l'ImpactZone produite par ImpactAnalyzer.
            contexts: les IncrementalContexts (gauche et droit, tous deux exacts).
            instance: la ProblemInstance de reference.

        Returns:
            WindowResult dont le `schedule` ne contient QUE les entrees de la zone
            reoptimisee, ou None si CP-SAT n'a trouve aucune solution.
        """
        debut = time.time()
        sub_instance, pending_ops = self._build_sub_instance(zone, instance)
        if not pending_ops:
            return self._empty_result(zone, sub_instance, debut)

        t_now = zone.state.t_now
        horizon = self._horizon(zone, pending_ops, contexts, sub_instance)
        model = cp_model.CpModel()

        op_vars = self._declare_operations(model, pending_ops, t_now, horizon)
        self._add_precedences(model, zone, sub_instance, op_vars)
        self._add_left_boundary(model, contexts.left, sub_instance, op_vars)
        obstacles, cibles = self._build_untouched_obstacles(
            model, zone, sub_instance, t_now
        )
        setup_vars = self._add_setups(model, sub_instance, op_vars, t_now, horizon)
        junction_vars = self._add_junction_setups(
            model, sub_instance, op_vars, cibles, t_now, horizon
        )
        self._add_no_overlap(model, zone, sub_instance, op_vars, setup_vars, obstacles,
                             junction_vars)
        self._add_cumulative_wr(model, zone, sub_instance, contexts.left, setup_vars,
                                horizon, junction_vars)
        tardiness_vars, completion_vars = self._add_tardiness(
            model, sub_instance, op_vars, horizon
        )
        self._set_objective(model, zone, sub_instance, op_vars, tardiness_vars, horizon)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(self.timeout_seconds)
        solver.parameters.num_search_workers = self.num_search_workers
        status = solver.Solve(model)
        elapsed = time.time() - debut
        logger.info(
            "IncrementalOptimizer status=%s en %.2fs (%d job(s), %d operation(s), "
            "stability_weight=%s)",
            solver.StatusName(status), elapsed, len(sub_instance.jobs),
            len(pending_ops), self.stability_weight,
        )
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            logger.warning(
                "Aucune solution sur la zone d'impact (%d obstacle(s) non touche(s))",
                sum(len(v) for v in obstacles.values()),
            )
            return None

        schedule = self._build_schedule(
            solver, zone, sub_instance, op_vars, setup_vars, contexts.left,
            tardiness_vars, completion_vars, status,
        )
        junction_setups = self._collect_junction_setups(solver, junction_vars)
        return WindowResult(
            window=Window(
                index=0, t_start=t_now, t_end=schedule.horizon,
                jobs=list(sub_instance.jobs),
            ),
            schedule=schedule,
            exit_context=schedule.exit_context,
            objective=solver.ObjectiveValue() / WEIGHT_SCALE,
            method="incremental",
            duration_seconds=round(elapsed, 3),
            junction_setups=junction_setups,
        )

    # -- sous-instance -------------------------------------------------------
    def _build_sub_instance(self, zone, instance):
        """Construit l'instance restreinte a la zone : jobs impactes, operations
        encore a placer, et les modifications portees par l'evenement lui-meme.

        Les operations figees ne sont JAMAIS des variables : pour un job a cheval
        sur T_now, seules ses operations futures entrent dans le modele.
        """
        event = zone.event
        jobs_by_id = {j.id: j for j in instance.jobs}

        # Positions encore a placer, par job, d'apres les entrees futures de la zone.
        positions_a_placer = {}
        for entry in zone.impacted_entries:
            positions_a_placer.setdefault(entry.job_id, set()).add(entry.position_in_job)

        annule = (
            event.payload.job_id
            if event.event_type is PerturbationType.JOB_CANCEL else None
        )

        sub_jobs, pending_ops = [], []
        for job_id in zone.impacted_job_ids:
            if job_id == annule:
                continue  # le job annule disparait du planning
            job = jobs_by_id.get(job_id)
            if job is None:
                continue
            ops = [
                op for op in job.operations
                if op.position in positions_a_placer.get(job_id, set())
            ]
            if not ops:
                continue
            ops = [self._apply_duration_change(op, event) for op in ops]
            sub_jobs.append(Job(id=job.id, operations=ops,
                                deadline=job.deadline, weight=job.weight))
            pending_ops.extend((job.id, op) for op in ops)

        # Le job urgent n'est pas dans le planning courant : toutes ses operations
        # sont a placer.
        if event.event_type is PerturbationType.URGENT_JOB:
            payload = event.payload
            ops = sorted(payload.operations, key=lambda o: o.position)
            sub_jobs.append(Job(id=payload.job_id, operations=ops,
                                deadline=payload.deadline, weight=payload.weight))
            pending_ops.extend((payload.job_id, op) for op in ops)

        sub_instance = ProblemInstance(
            jobs=sub_jobs,
            machines=list(instance.machines),
            setup_times=instance.setup_times,
            wr=instance.wr,
        )
        return sub_instance, pending_ops

    @staticmethod
    def _apply_duration_change(op, event):
        """La duree reelle constatee remplace la duree prevue."""
        if event.event_type is not PerturbationType.DURATION_CHANGE:
            return op
        payload = event.payload
        if op.job_id == payload.job_id and op.position == payload.position_in_job:
            return type(op)(op.job_id, op.machine_id, payload.new_duration, op.position)
        return op

    @staticmethod
    def _horizon(zone, pending_ops, contexts, sub_instance) -> int:
        """Borne superieure large mais finie pour les variables de temps.

        Assez grande pour ne jamais couper une solution : la fin la plus tardive
        connue, plus la totalite du travail restant et des setups possibles.
        """
        base = zone.state.t_now
        for entry in zone.impacted_entries:
            base = max(base, entry.end_time)
        for borne in contexts.right.machine_loads.values():
            base = max(base, borne)
        for entry in zone.untouched_future_entries:
            base = max(base, entry.end_time)
        travail = sum(op.duration for _, op in pending_ops)
        jobs_zone = {j.id for j in sub_instance.jobs}
        setups = sum(
            duree for (from_j, to_j, _), duree in sub_instance.setup_times.items()
            if from_j in jobs_zone and to_j in jobs_zone
        )
        return base + travail + setups + 1

    # -- construction du modele ---------------------------------------------
    @staticmethod
    def _declare_operations(model, pending_ops, t_now, horizon) -> dict:
        """Une variable d'intervalle par operation a placer, jamais avant T_now."""
        op_vars = {}
        for job_id, op in pending_ops:
            s = model.NewIntVar(t_now, horizon, f"s_{job_id}_{op.position}")
            e = model.NewIntVar(t_now, horizon, f"e_{job_id}_{op.position}")
            iv = model.NewIntervalVar(s, op.duration, e, f"iv_{job_id}_{op.position}")
            op_vars[(job_id, op.position)] = (s, e, iv, op)
        return op_vars

    @staticmethod
    def _add_precedences(model, zone, sub_instance, op_vars) -> None:
        """Precedence interne au job, y compris apres la partie figee.

        Pour un job a cheval sur T_now, la premiere operation encore a placer ne
        peut pas demarrer avant la fin de sa derniere operation figee — l'operation
        en cours est un fait accompli, pas une variable.
        """
        fin_figee_par_job = {}
        for entry in zone.state.frozen_entries:
            fin = entry.end_time
            if fin > fin_figee_par_job.get(entry.job_id, 0):
                fin_figee_par_job[entry.job_id] = fin

        for job in sub_instance.jobs:
            ops = sorted(job.operations, key=lambda o: o.position)
            for k in range(len(ops) - 1):
                _, e1, _, _ = op_vars[(job.id, ops[k].position)]
                s2, _, _, _ = op_vars[(job.id, ops[k + 1].position)]
                model.Add(s2 >= e1)
            fin_figee = fin_figee_par_job.get(job.id)
            if fin_figee is not None and ops:
                s_first, _, _, _ = op_vars[(job.id, ops[0].position)]
                model.Add(s_first >= fin_figee)

    @staticmethod
    def _add_left_boundary(model, left, sub_instance, op_vars) -> None:
        """Contexte gauche EXACT : chaque machine n'est libre qu'a sa charge figee.

        Si le dernier job fige de la machine differe du job a placer, un setup les
        separe. On applique la meme convention que `CPSATSolver.solve_with_context` :
        la contrainte porte sur toutes les operations de la machine, pas seulement
        sur la premiere — conservateur, mais coherent avec le solveur initial.
        """
        for (job_id, _), (s, _, _, op) in op_vars.items():
            charge = left.machine_loads.get(op.machine_id, 0)
            model.Add(s >= charge)
            dernier = left.last_job_per_machine.get(op.machine_id)
            if dernier and dernier != job_id:
                s_dur = sub_instance.get_setup(dernier, job_id, op.machine_id)
                if s_dur > 0:
                    model.Add(s >= charge + s_dur)

    @staticmethod
    def _build_untouched_obstacles(model, zone, sub_instance, t_now):
        """Contexte droit EXACT et CONTRAIGNANT : le futur non touche est un obstacle.

        Le futur non touche n'est PAS une simple date butoir apres laquelle la zone
        devrait tenir : sur une machine donnee, operations de la zone et operations
        non touchees s'entrelacent. Les forcer toutes avant la premiere operation
        non touchee est structurellement impossible des que l'entrelacement existe.

        La modelisation correcte est de traiter chaque operation non touchee comme
        un INTERVALLE FIXE occupant sa machine. La zone peut alors se placer avant,
        entre, ou apres, mais jamais dessus — ce qui garantit par construction
        l'absence de chevauchement a la frontiere droite, critere d'acceptation du
        ScheduleMerger.

        Deux regimes en AMONT de l'obstacle, depuis la resolution de H7 (cf. D8) :

        - La PREMIERE entree non touchee d'une machine ou la zone a des operations
          est la JONCTION : son setup peut changer, puisque la zone peut lui donner
          un nouveau predecesseur. Son obstacle ne couvre donc que l'OPERATION
          ([start_time, end_time]) ; la place du setup est laissee libre et devient
          une variable du modele (cf. _add_junction_setups).
        - Toutes les autres entrees non touchees gardent leur predecesseur d'origine :
          leur obstacle couvre l'occupation complete (setup inclus) et reste elargi
          vers l'amont de la duree du setup entrant le plus long qu'un job de la zone
          pourrait exiger — reservation conservatrice.

        Un SEUL regime en AVAL, applique a TOUTES les entrees non touchees, jonction
        comprise (cf. D10) : l'obstacle est elargi vers l'aval de la duree du setup
        SORTANT le plus long qu'exigerait un job de la zone place juste derriere.
        Sans cette garde, une operation de la zone pouvait se coller a la fin d'une
        entree non touchee sans laisser la place a son setup entrant, produisant un
        planning infaisable en atelier que le validateur canonique ne detectait pas
        (il ne verifie ni le predecesseur reel d'un setup ni sa duree). C'est le
        defaut trouve par le livrable 1 de la Discussion 2.

        Les deux gardes sont de meme nature — une reservation conservatrice bornee
        par le plus long setup possible — et couvrent desormais les deux sens de
        transition entre la zone et le futur non touche :

            [zone] --garde amont--> [non touchee] --garde aval--> [zone]

        Les elargissements sont bornes par la fin de l'obstacle precedent sur la meme
        machine, sans quoi deux obstacles se chevaucheraient et rendraient le
        NoOverlap infaisable.

        Returns:
            (obstacles, cibles) ou obstacles = {machine_id: [IntervalVar fixes]} et
            cibles = {machine_id: entree de jonction} pour les machines concernees.
        """
        obstacles, cibles = {}, {}
        par_machine = {}
        for entry in zone.untouched_future_entries:
            par_machine.setdefault(entry.machine_id, []).append(entry)

        machines_zone = {
            op.machine_id for job in sub_instance.jobs for op in job.operations
        }

        for machine_id, entrees in par_machine.items():
            entrees.sort(key=_occupation_start)
            fin_precedente = t_now
            intervalles = []
            for rang, entry in enumerate(entrees):
                jonction = rang == 0 and machine_id in machines_zone
                if jonction:
                    # Le setup de cette entree redevient une variable : l'obstacle
                    # ne couvre que l'operation, la place du setup est liberee.
                    cibles[machine_id] = entry
                    debut_reel, garde = entry.start_time, 0
                else:
                    debut_reel = _occupation_start(entry)
                    garde = max(
                        (sub_instance.get_setup(job.id, entry.job_id, machine_id)
                         for job in sub_instance.jobs),
                        default=0,
                    )
                # Garde AVAL (cf. D10), appliquee a tout regime : reserve la place
                # du setup entrant d'une operation de zone qui se placerait juste
                # derriere cette entree non touchee.
                garde_aval = max(
                    (sub_instance.get_setup(entry.job_id, job.id, machine_id)
                     for job in sub_instance.jobs),
                    default=0,
                )
                debut = max(fin_precedente, debut_reel - garde, t_now)
                fin = max(entry.end_time + garde_aval, debut)
                intervalles.append(model.NewIntervalVar(
                    model.NewConstant(debut), fin - debut, model.NewConstant(fin),
                    f"intouche_{machine_id}_{entry.job_id}_{entry.position_in_job}",
                ))
                fin_precedente = fin
            obstacles[machine_id] = intervalles
        return obstacles, cibles

    @staticmethod
    def _add_junction_setups(model, sub_instance, op_vars, cibles, t_now, horizon):
        """Setups de jonction zone -> premier job non touche, en VARIABLES (D8).

        Resout H7. La version precedente se contentait de reserver la place de ces
        setups en elargissant les obstacles vers l'amont, sans variable : leurs dates
        n'existaient donc pas, et aucun SetupEntry n'etait emis a la jonction. Les
        fabriquer apres coup a partir de left.machine_loads avait ete essaye et
        rejete — les dates obtenues chevauchaient le planning existant.

        Ici la place du setup de jonction est un intervalle OPTIONNEL du modele,
        donc soumis au NoOverlap de la machine et a la Cumulative WR, exactement
        comme les setups internes a la zone. Ses dates sortent du solveur.

        Le predecesseur de l'entree de jonction est choisi par le modele, parmi les
        jobs de la zone presents sur la machine, plus l'option "predecesseur
        d'origine inchange". Un seul est retenu (AddExactlyOne), et c'est
        necessairement l'operation de zone qui finit au plus tard avant la jonction :
        sans cette contrainte, CP-SAT pourrait designer un predecesseur a setup nul
        et economiser un temps de setup qui doit pourtant etre paye.

        Returns:
            {machine_id: (cible, [(job_id, b, ss, se, duree, iv)], b_origine)}
        """
        junction_vars = {}
        for machine_id, cible in cibles.items():
            op_debut = cible.start_time
            candidats = [
                job for job in sub_instance.jobs
                if any(op.machine_id == machine_id for op in job.operations)
            ]
            if not candidats:
                continue

            # -- "l'operation de zone qui finit au plus tard avant la jonction" ----
            # fin_eff vaut la fin de l'operation quand elle precede la jonction, et
            # t_now sinon : le maximum des fin_eff designe donc le predecesseur reel,
            # ou vaut t_now si aucune operation de zone ne precede la jonction.
            fins_eff, avant = {}, {}
            for job in candidats:
                e_var = _var_on_machine(op_vars, job.id, machine_id, index=1)
                a = model.NewBoolVar(f"avant_{job.id}_{machine_id}")
                model.Add(e_var <= op_debut).OnlyEnforceIf(a)
                model.Add(e_var > op_debut).OnlyEnforceIf(a.Not())
                fe = model.NewIntVar(t_now, horizon, f"fineff_{job.id}_{machine_id}")
                model.Add(fe == e_var).OnlyEnforceIf(a)
                model.Add(fe == t_now).OnlyEnforceIf(a.Not())
                fins_eff[job.id], avant[job.id] = fe, a

            dernier = model.NewIntVar(t_now, horizon, f"dernier_{machine_id}")
            model.AddMaxEquality(dernier, list(fins_eff.values()) + [t_now])

            b_origine = model.NewBoolVar(f"jonction_origine_{machine_id}")
            # Le predecesseur d'origine ne subsiste que si aucune operation de la
            # zone ne vient s'intercaler avant la jonction.
            model.Add(dernier == t_now).OnlyEnforceIf(b_origine)

            choix = []
            for job in candidats:
                b = model.NewBoolVar(f"jonction_{job.id}_{machine_id}")
                model.AddImplication(b, avant[job.id])
                model.Add(fins_eff[job.id] == dernier).OnlyEnforceIf(b)
                model.Add(dernier > t_now).OnlyEnforceIf(b)
                duree = sub_instance.get_setup(job.id, cible.job_id, machine_id)
                ss = se = iv = None
                if duree > 0:
                    e_var = _var_on_machine(op_vars, job.id, machine_id, index=1)
                    ss = model.NewIntVar(t_now, horizon, f"jss_{job.id}_{machine_id}")
                    se = model.NewIntVar(t_now, horizon, f"jse_{job.id}_{machine_id}")
                    iv = model.NewOptionalIntervalVar(
                        ss, duree, se, b, f"jiv_{job.id}_{machine_id}"
                    )
                    # Le setup s'intercale entre la fin de l'operation de zone et le
                    # debut de l'operation non touchee, dont la date est fixe.
                    model.Add(ss >= e_var).OnlyEnforceIf(b)
                    model.Add(se <= op_debut).OnlyEnforceIf(b)
                choix.append((job.id, b, ss, se, duree, iv))

            # L'entree de jonction a exactement un predecesseur : un job de la zone,
            # ou celui d'origine.
            model.AddExactlyOne([b for _, b, _, _, _, _ in choix] + [b_origine])

            # Le setup d'origine n'occupe la machine que s'il subsiste.
            if cible.setup and cible.setup.duration > 0:
                model.NewOptionalIntervalVar(
                    model.NewConstant(cible.setup.start_time),
                    cible.setup.duration,
                    model.NewConstant(cible.setup.end_time),
                    b_origine, f"jonction_setup_origine_{machine_id}",
                )
            junction_vars[machine_id] = (cible, choix, b_origine)
        return junction_vars

    @staticmethod
    def _add_setups(model, sub_instance, op_vars, t_now, horizon) -> dict:
        """Setups sequence-dependants entre operations de la zone sur une machine."""
        setup_vars = {}
        for machine_id in sub_instance.machines:
            jobs_on_m = [
                j for j in sub_instance.jobs
                if any(op.machine_id == machine_id for op in j.operations)
            ]
            for from_job in jobs_on_m:
                for to_job in jobs_on_m:
                    if from_job.id == to_job.id:
                        continue
                    s_dur = sub_instance.get_setup(from_job.id, to_job.id, machine_id)
                    if s_dur == 0:
                        continue
                    b = model.NewBoolVar(f"b_{from_job.id}_{to_job.id}_{machine_id}")
                    ss = model.NewIntVar(t_now, horizon,
                                         f"ss_{from_job.id}_{to_job.id}_{machine_id}")
                    se = model.NewIntVar(t_now, horizon,
                                         f"se_{from_job.id}_{to_job.id}_{machine_id}")
                    siv = model.NewOptionalIntervalVar(
                        ss, s_dur, se, b, f"siv_{from_job.id}_{to_job.id}_{machine_id}"
                    )
                    setup_vars[(from_job.id, to_job.id, machine_id)] = (ss, se, siv, b, s_dur)

                    ef = _var_on_machine(op_vars, from_job.id, machine_id, index=1)
                    st = _var_on_machine(op_vars, to_job.id, machine_id, index=0)
                    if ef is not None and st is not None:
                        model.Add(ss >= ef).OnlyEnforceIf(b)
                        model.Add(st >= se).OnlyEnforceIf(b)
        return setup_vars

    @staticmethod
    def _add_no_overlap(model, zone, sub_instance, op_vars, setup_vars,
                        obstacles, junction_vars=None) -> None:
        """NoOverlap par machine : operations, setups, obstacles, panne.

        Quatre sources d'occupation en plus des operations de la zone : leurs
        setups, les setups de jonction vers le futur non touche (cf. D8), les
        operations futures non touchees (obstacles fixes, cf.
        _build_untouched_obstacles) et, le cas echeant, la fenetre
        d'indisponibilite d'une machine en panne.
        """
        event = zone.event
        for machine_id in sub_instance.machines:
            intervals = [
                iv for (_, _), (_, _, iv, op) in op_vars.items()
                if op.machine_id == machine_id
            ]
            intervals += [
                siv for (_, _, km), (_, _, siv, _, _) in setup_vars.items()
                if km == machine_id
            ]
            intervals += obstacles.get(machine_id, [])
            intervals += _junction_intervals(model, junction_vars, machine_id)
            if (event.event_type is PerturbationType.MACHINE_BREAKDOWN
                    and event.payload.machine_id == machine_id):
                payload = event.payload
                intervals.append(model.NewIntervalVar(
                    model.NewConstant(payload.start_time),
                    payload.end_time - payload.start_time,
                    model.NewConstant(payload.end_time),
                    f"panne_{machine_id}",
                ))
            if intervals:
                model.AddNoOverlap(intervals)

    @staticmethod
    def _add_cumulative_wr(model, zone, sub_instance, left, setup_vars, horizon,
                           junction_vars=None) -> None:
        """Contrainte Cumulative sur les setups (WR techniciens).

        Quatre sources de demande : les setups de la zone, les setups de jonction
        vers le futur non touche (cf. D8), les setups figes encore actifs a T_now
        (contexte gauche exact), et — pour un evenement
        resource_change — un intervalle fixe qui consomme la capacite retiree
        pendant la fenetre, ce qui revient exactement a abaisser le WR sur cette
        periode sans avoir a rendre la capacite variable dans le temps.
        """
        intervals, demands = [], []
        for (_, _, _), (_, _, siv, _, _) in setup_vars.items():
            intervals.append(siv)
            demands.append(1)

        for machine_id in (junction_vars or {}):
            for iv in _junction_intervals(model, junction_vars, machine_id):
                intervals.append(iv)
                demands.append(1)

        for machine_id, from_j, to_j, s_time, e_time in left.active_setups:
            if e_time > s_time:
                intervals.append(model.NewIntervalVar(
                    model.NewConstant(s_time), e_time - s_time,
                    model.NewConstant(e_time),
                    f"setup_actif_{machine_id}_{from_j}_{to_j}",
                ))
                demands.append(1)

        event = zone.event
        if event.event_type is PerturbationType.RESOURCE_CHANGE:
            payload = event.payload
            retire = sub_instance.wr - payload.new_wr
            if retire > 0:
                intervals.append(model.NewIntervalVar(
                    model.NewConstant(payload.start_time),
                    payload.end_time - payload.start_time,
                    model.NewConstant(payload.end_time),
                    "wr_indisponible",
                ))
                demands.append(retire)

        if intervals and sub_instance.wr > 0:
            model.AddCumulative(intervals, demands, sub_instance.wr)

    @staticmethod
    def _add_tardiness(model, sub_instance, op_vars, horizon):
        """Retard de chaque job de la zone, depuis la fin de sa derniere operation."""
        tardiness_vars, completion_vars = {}, {}
        zero = model.NewConstant(0)
        for job in sub_instance.jobs:
            derniere = max(job.operations, key=lambda o: o.position)
            _, e_last, _, _ = op_vars[(job.id, derniere.position)]
            completion_vars[job.id] = e_last
            t = model.NewIntVar(0, horizon, f"tard_{job.id}")
            model.AddMaxEquality(t, [e_last - job.deadline, zero])
            tardiness_vars[job.id] = t
        return tardiness_vars, completion_vars

    def _set_objective(self, model, zone, sub_instance, op_vars, tardiness_vars,
                       horizon) -> None:
        """Retard pondere + penalite de stabilite (valeur absolue linearisee).

        La valeur absolue |debut_nouveau - debut_original| n'est PAS ecrite avec un
        abs() : elle est linearisee de facon standard en CP-SAT avec deux variables
        auxiliaires par job, delta_plus et delta_moins, liees par

            delta_plus - delta_moins = debut_nouveau - debut_original

        et penalisees toutes les deux. La minimisation force l'une des deux a zero,
        donc delta_plus + delta_moins vaut exactement l'ecart absolu.
        """
        termes = [
            int(job.weight * WEIGHT_SCALE) * tardiness_vars[job.id]
            for job in sub_instance.jobs
        ]

        poids_stabilite = int(round(self.stability_weight * WEIGHT_SCALE))
        if poids_stabilite > 0:
            debuts_originaux = self._original_starts(zone)
            for job in sub_instance.jobs:
                premiere = min(job.operations, key=lambda o: o.position)
                origine = debuts_originaux.get((job.id, premiere.position))
                if origine is None:
                    continue  # job urgent : aucun debut original de reference
                s, _, _, _ = op_vars[(job.id, premiere.position)]
                delta_plus = model.NewIntVar(0, horizon, f"dplus_{job.id}")
                delta_moins = model.NewIntVar(0, horizon, f"dmoins_{job.id}")
                model.Add(delta_plus - delta_moins == s - origine)
                termes.append(poids_stabilite * delta_plus)
                termes.append(poids_stabilite * delta_moins)

        model.Minimize(sum(termes))

    @staticmethod
    def _original_starts(zone) -> dict:
        """{(job_id, position): debut dans le planning d'origine}."""
        return {
            (e.job_id, e.position_in_job): e.start_time
            for e in zone.state.future_entries
        }

    # -- extraction du resultat ---------------------------------------------
    def _build_schedule(self, solver, zone, sub_instance, op_vars, setup_vars, left,
                        tardiness_vars, completion_vars, status) -> Schedule:
        schedule = Schedule(
            method_used="incremental",
            solver_status="optimal" if status == cp_model.OPTIMAL else "feasible",
        )
        eligibles = self._eligibles_jonction_gauche(solver, zone, op_vars)
        for job in sub_instance.jobs:
            for op in job.operations:
                s, e, _, _ = op_vars[(job.id, op.position)]
                schedule.add_entry(ScheduleEntry(
                    job_id=job.id, machine_id=op.machine_id, position_in_job=op.position,
                    start_time=solver.Value(s), end_time=solver.Value(e),
                    duration=op.duration,
                    setup=self._setup_entry_for(solver, job.id, op, setup_vars, left,
                                                sub_instance, eligibles),
                ))
        total = 0.0
        for job in sub_instance.jobs:
            tard = solver.Value(tardiness_vars[job.id])
            wt = round(job.weight * tard, 4)
            total += wt
            schedule.jobs_result.append(JobResult(
                job_id=job.id, deadline=job.deadline, weight=job.weight,
                completion_time=solver.Value(completion_vars[job.id]),
                tardiness=tard, is_late=tard > 0, weighted_tardiness=wt,
            ))
        schedule.total_weighted_tardiness = round(total, 4)
        schedule.exit_context = self._exit_context(schedule, sub_instance)
        return schedule

    @staticmethod
    def _setup_entry_for(solver, job_id, op, setup_vars, left, sub_instance,
                         eligibles_jonction_gauche):
        """SetupEntry d'une operation, uniquement quand il est reellement modelise.

        Deux cas seulement produisent un setup :

        1. un setup INTERNE a la zone, porte par une variable optionnelle du modele :
           il est deja dans le NoOverlap et dans la Cumulative, ses dates sont sures ;
        2. le setup de jonction GAUCHE (dernier job fige -> premier job de la zone),
           dont la place est reservee par la contrainte `s >= charge + duree` — mais
           seulement si cette operation est bien la premiere a occuper sa machine
           apres T_now.

        Le troisieme cas — un setup a la jonction avec une operation non touchee —
        n'est pas traite ici, mais il n'est plus une limite : depuis D8 il est
        modelise par des variables optionnelles (cf. _add_junction_setups) et
        remonte par `WindowResult.junction_setups`, car il precede une operation qui
        n'appartient pas a la zone et ne peut donc pas etre porte par une entree de
        ce Schedule.
        """
        for (fi, ti, km), (ss, se, _, b, sd) in setup_vars.items():
            if ti == job_id and km == op.machine_id and solver.Value(b) == 1:
                return SetupEntry(from_job_id=fi, start_time=solver.Value(ss),
                                  end_time=solver.Value(se), duration=sd)

        if (op.machine_id, job_id, op.position) not in eligibles_jonction_gauche:
            return None
        dernier = left.last_job_per_machine.get(op.machine_id)
        if dernier and dernier != job_id:
            s_dur = sub_instance.get_setup(dernier, job_id, op.machine_id)
            if s_dur > 0:
                charge = left.machine_loads.get(op.machine_id, 0)
                return SetupEntry(from_job_id=dernier, start_time=charge,
                                  end_time=charge + s_dur, duration=s_dur)
        return None

    @staticmethod
    def _collect_junction_setups(solver, junction_vars) -> dict:
        """SetupEntry de jonction retenus, indexes par l'entree non touchee visee.

        Ces setups precedent une operation qui n'appartient PAS a la zone : ils ne
        peuvent donc pas etre portes par le Schedule renvoye ici, qui ne contient
        que les entrees reoptimisees. Ils remontent par le WindowResult, et c'est le
        ScheduleMerger qui les rattache a l'entree non touchee correspondante.

        Rien n'est emis quand le predecesseur d'origine subsiste (b_origine) ou
        quand la transition retenue a un setup de duree nulle.
        """
        junction_setups = {}
        for _machine_id, (cible, choix, b_origine) in junction_vars.items():
            if solver.Value(b_origine) == 1:
                continue
            for job_id, b, ss, se, duree, _iv in choix:
                if solver.Value(b) != 1 or duree <= 0:
                    continue
                junction_setups[(cible.job_id, cible.position_in_job)] = SetupEntry(
                    from_job_id=job_id,
                    start_time=solver.Value(ss),
                    end_time=solver.Value(se),
                    duration=duree,
                )
        return junction_setups

    @staticmethod
    def _eligibles_jonction_gauche(solver, zone, op_vars) -> set:
        """Operations de la zone reellement premieres sur leur machine apres T_now.

        Une operation n'herite du setup de jonction gauche que si aucune operation
        non touchee ne l'y precede : sinon son vrai predecesseur sur la machine
        n'est pas le dernier job fige, et le setup calcule serait faux.
        """
        premier_intouche = {}
        for entry in zone.untouched_future_entries:
            debut = _occupation_start(entry)
            actuel = premier_intouche.get(entry.machine_id)
            if actuel is None or debut < actuel:
                premier_intouche[entry.machine_id] = debut

        premier_zone = {}
        for (job_id, position), (s, _, _, op) in op_vars.items():
            debut = solver.Value(s)
            actuel = premier_zone.get(op.machine_id)
            if actuel is None or debut < actuel[0]:
                premier_zone[op.machine_id] = (debut, job_id, position)

        eligibles = set()
        for machine_id, (debut, job_id, position) in premier_zone.items():
            borne = premier_intouche.get(machine_id)
            if borne is None or debut < borne:
                eligibles.add((machine_id, job_id, position))
        return eligibles

    @staticmethod
    def _exit_context(schedule, sub_instance):
        from scheduling.models.context import BoundaryContext

        last_job_per_machine, machine_loads = {}, {}
        for machine_id in sub_instance.machines:
            entrees = [e for e in schedule.entries if e.machine_id == machine_id]
            if entrees:
                derniere = max(entrees, key=lambda e: e.end_time)
                last_job_per_machine[machine_id] = derniere.job_id
                machine_loads[machine_id] = derniere.end_time
        return BoundaryContext(
            last_job_per_machine=last_job_per_machine, active_setups=[],
            pending_jobs=list({e.job_id for e in schedule.entries}),
            machine_loads=machine_loads,
        )

    @staticmethod
    def _empty_result(zone, sub_instance, debut) -> WindowResult:
        """Zone sans aucune operation a replanifier : resultat vide mais valide."""
        schedule = Schedule(method_used="incremental", solver_status="empty")
        return WindowResult(
            window=Window(index=0, t_start=zone.state.t_now, t_end=zone.state.t_now,
                          jobs=list(sub_instance.jobs)),
            schedule=schedule,
            exit_context=None,
            objective=0.0,
            method="incremental",
            duration_seconds=round(time.time() - debut, 3),
        )


def _junction_intervals(model, junction_vars, machine_id) -> list:
    """Intervalles optionnels des setups de jonction d'une machine (cf. D8).

    Ce sont les intervalles DEJA declares par _add_junction_setups : en recreer
    ici sur les memes variables produirait deux intervalles actifs simultanement,
    donc un NoOverlap infaisable.
    """
    if not junction_vars or machine_id not in junction_vars:
        return []
    _cible, choix, _b_origine = junction_vars[machine_id]
    return [iv for _jid, _b, _ss, _se, _duree, iv in choix if iv is not None]


def _var_on_machine(op_vars, job_id, machine_id, index):
    """Variable de debut (index=0) ou de fin (index=1) de l'operation d'un job
    sur une machine donnee, ou None si ce job n'y a pas d'operation dans la zone."""
    for (jid, _), (s, e, _, op) in op_vars.items():
        if jid == job_id and op.machine_id == machine_id:
            return s if index == 0 else e
    return None
