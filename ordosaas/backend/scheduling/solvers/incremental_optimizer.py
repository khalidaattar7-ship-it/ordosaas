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
        right_reserve = self._add_right_boundary(
            model, contexts.right, sub_instance, op_vars
        )
        setup_vars = self._add_setups(model, sub_instance, op_vars, t_now, horizon)
        self._add_no_overlap(model, zone, sub_instance, op_vars, setup_vars)
        self._add_cumulative_wr(model, zone, sub_instance, contexts.left, setup_vars,
                                horizon)
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
                "Aucune solution sur la zone d'impact (reserve de setup droite : %s)",
                right_reserve,
            )
            return None

        schedule = self._build_schedule(
            solver, zone, sub_instance, op_vars, setup_vars, contexts.left,
            tardiness_vars, completion_vars, status,
        )
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

    def _add_right_boundary(self, model, right, sub_instance, op_vars) -> int:
        """Contexte droit EXACT et CONTRAIGNANT : la zone ne deborde pas dessus.

        Une reserve est retranchee a la borne pour laisser place au setup entre la
        derniere operation de la zone et la premiere operation non touchee de la
        machine. Cette reserve est volontairement conservatrice (le setup le plus
        long possible vers ce job) : cela peut couter un peu de compacite, mais
        garantit qu'aucune fusion ne produira de chevauchement a la frontiere
        droite — c'est le critere d'acceptation du ScheduleMerger.
        """
        reserves = {}
        for machine_id, borne in right.machine_loads.items():
            job_suivant = right.last_job_per_machine.get(machine_id)
            reserve = 0
            if job_suivant:
                for job in sub_instance.jobs:
                    reserve = max(
                        reserve,
                        sub_instance.get_setup(job.id, job_suivant, machine_id),
                    )
            reserves[machine_id] = reserve
            for (_, _), (_, e, _, op) in op_vars.items():
                if op.machine_id == machine_id:
                    model.Add(e <= borne - reserve)
        return reserves

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
    def _add_no_overlap(model, zone, sub_instance, op_vars, setup_vars) -> None:
        """NoOverlap par machine : operations, setups, et machine indisponible.

        Une panne machine est modelisee comme un intervalle fixe occupant la
        machine : aucune operation ne peut y etre placee.
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
    def _add_cumulative_wr(model, zone, sub_instance, left, setup_vars, horizon) -> None:
        """Contrainte Cumulative sur les setups (WR techniciens).

        Trois sources de demande : les setups de la zone, les setups figes encore
        actifs a T_now (contexte gauche exact), et — pour un evenement
        resource_change — un intervalle fixe qui consomme la capacite retiree
        pendant la fenetre, ce qui revient exactement a abaisser le WR sur cette
        periode sans avoir a rendre la capacite variable dans le temps.
        """
        intervals, demands = [], []
        for (_, _, _), (_, _, siv, _, _) in setup_vars.items():
            intervals.append(siv)
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
        for job in sub_instance.jobs:
            for op in job.operations:
                s, e, _, _ = op_vars[(job.id, op.position)]
                schedule.add_entry(ScheduleEntry(
                    job_id=job.id, machine_id=op.machine_id, position_in_job=op.position,
                    start_time=solver.Value(s), end_time=solver.Value(e),
                    duration=op.duration,
                    setup=self._setup_entry_for(solver, job.id, op, setup_vars, left,
                                                sub_instance),
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
    def _setup_entry_for(solver, job_id, op, setup_vars, left, sub_instance):
        for (fi, ti, km), (ss, se, _, b, sd) in setup_vars.items():
            if ti == job_id and km == op.machine_id and solver.Value(b) == 1:
                return SetupEntry(from_job_id=fi, start_time=solver.Value(ss),
                                  end_time=solver.Value(se), duration=sd)
        dernier = left.last_job_per_machine.get(op.machine_id)
        if dernier and dernier != job_id:
            s_dur = sub_instance.get_setup(dernier, job_id, op.machine_id)
            if s_dur > 0:
                charge = left.machine_loads.get(op.machine_id, 0)
                return SetupEntry(from_job_id=dernier, start_time=charge,
                                  end_time=charge + s_dur, duration=s_dur)
        return None

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


def _var_on_machine(op_vars, job_id, machine_id, index):
    """Variable de debut (index=0) ou de fin (index=1) de l'operation d'un job
    sur une machine donnee, ou None si ce job n'y a pas d'operation dans la zone."""
    for (jid, _), (s, e, _, op) in op_vars.items():
        if jid == job_id and op.machine_id == machine_id:
            return s if index == 0 else e
    return None
