"""
ImpactAnalyzer : determine la zone du planning a re-optimiser apres une perturbation.

Trois sources d'impact, cumulees (cf. docs/architecture-incremental.md Sec. 2.4) :

1. Impact DIRECT     - les operations que l'evenement touche lui-meme (operations
                       prevues sur la machine en panne pendant la fenetre
                       d'indisponibilite, operation dont la duree change, ...).
2. Cascade PRECEDENCE - les operations en aval du meme job : si une operation est
                       repoussee, les suivantes du job le sont aussi.
3. Cascade CONTENTION - les jobs qui devront se decaler sur une machine partagee.

La cascade de contention n'est pas une fermeture transitive aveugle (qui rouvrirait
tout le planning pour un incident local) : elle simule l'absorption du retard. Un
retard de D unites se propage au job suivant sur la machine uniquement si le temps
mort qui le precede ne suffit pas a l'absorber, et se propage alors reduit du temps
mort consomme. Un incident court tombant dans un planning aere s'eteint donc de
lui-meme apres quelques operations.

Le tout est borne par un horizon de recherche configurable, pour garantir qu'aucune
perturbation ne puisse rouvrir tout le planning futur.

UNITE DE TEMPS (decision D7) : les start_time / end_time / duration du projet sont
des entiers SANS unite physique. Les bornes sont donc exprimees en FRACTIONS de
l'instance traitee, pas en valeurs absolues :

- `search_horizon_fraction` - part de l'horizon restant depuis T_now (defaut 0.15) ;
- `max_impacted_jobs_fraction` - part des jobs futurs (defaut 0.20).

Les deux acceptent une surcharge absolue (`search_horizon`, `max_impacted_jobs`) pour
les appels qui savent ce qu'ils font, mais ce n'est plus le mode par defaut.
"""
import logging
from dataclasses import dataclass, field

from scheduling.components.schedule_state_manager import ScheduleState, ScheduleStateManager
from scheduling.models.perturbation import PerturbationType

logger = logging.getLogger(__name__)

# Raisons d'appartenance a la zone d'impact, par ordre de priorite d'affichage.
REASON_DIRECT = "direct"
REASON_PRECEDENCE = "precedence"
REASON_CONTENTION = "machine_contention"

# Bornes par defaut de l'horizon de recherche, exprimees en fractions de l'instance
# traitee (cf. D7 : l'unite de temps du projet est abstraite). Ce sont les defauts du
# constructeur, surchargeables par appel — rien n'est code en dur dans la logique.
#
# Ces fractions remplacent les anciennes valeurs absolues DEFAULT_SEARCH_HORIZON = 240
# et DEFAULT_MAX_IMPACTED_JOBS = 30, qui supposaient implicitement la minute (240 = "4
# prochaines heures", 30 = "30 prochains jobs", cf. Sec. 2.4). Sur l'instance d'exemple
# — charge d'environ 460 unites par machine — 240 couvrait la moitie du planning : la
# borne censee contenir un incident local ne contenait plus rien, ce qui contribuait au
# sur-declenchement du garde-fou de repli.
DEFAULT_SEARCH_HORIZON_FRACTION = 0.15  # 15 % de l'horizon restant depuis T_now
DEFAULT_MAX_IMPACTED_JOBS_FRACTION = 0.20  # 20 % des jobs futurs restants

# Planchers, pour qu'une petite instance ne se retrouve pas avec une fenetre de
# recherche quasi nulle. Le plancher d'horizon par defaut est lui aussi sans unite :
# il vaut la plus longue occupation future, afin que la fenetre admette toujours au
# moins une operation entiere (cf. _plancher_horizon).
DEFAULT_MIN_IMPACTED_JOBS = 2  # le job perturbe, plus au moins un voisin de cascade
# Au-dela de cette part de jobs futurs touches, l'incremental perd son sens
# structurel : mieux vaut relancer un LNS complet (cf. Sec. 2.6).
DEFAULT_FALLBACK_THRESHOLD = 0.5


class IncrementalNotSuitableError(Exception):
    """La zone d'impact est trop large pour que l'incremental ait du sens.

    POINT D'EXTENSION (garde-fou de repli, Sec. 2.6). Cette exception SIGNALE
    que la perturbation depasse le seuil ; elle ne route rien. Le routage reel
    vers LNSRecursiveSolver dans SolverDispatcher est volontairement laisse pour
    une session ulterieure (hypothese H5 de docs/CONTEXTE_ET_DECISIONS.md).

    Le contrat attendu du futur appelant : rattraper cette exception et relancer
    une resolution complete, plutot que de forcer une resolution partielle
    degradee sur une zone qui couvre la moitie du planning.
    """

    def __init__(self, zone, threshold: float):
        self.zone = zone
        self.threshold = threshold
        self.ratio = zone.ratio_future_jobs_affected
        super().__init__(
            f"Zone d'impact trop large : {zone.nb_impacted_jobs} job(s) touche(s) "
            f"sur {zone.nb_future_jobs} futurs ({100 * self.ratio:.0f}%), seuil "
            f"{100 * threshold:.0f}%. Le reordonnancement incremental n'est pas "
            f"adapte a cette perturbation : relancer une resolution complete."
        )


@dataclass
class ImpactZone:
    """Zone du planning a re-optimiser, et le contexte pour la delimiter."""

    event: object  # PerturbationEvent
    t_now: int
    state: ScheduleState
    horizon_end: int
    # Bornes effectivement resolues pour cette analyse (cf. D7). Elles dependent du
    # planning et de T_now, pas seulement du constructeur : on les trace ici pour que
    # la zone reste lisible et verifiable apres coup.
    search_horizon: int = 0
    max_impacted_jobs: int = 0
    # job_id -> REASON_* (la raison la plus forte rencontree)
    reason_by_job: dict = field(default_factory=dict)
    # Entrees futures appartenant aux jobs impactes : ce sont elles qui redeviennent
    # des variables d'optimisation. Les entrees figees n'y sont jamais.
    impacted_entries: list = field(default_factory=list)
    # True si la propagation a ete coupee par une borne de l'horizon de recherche.
    truncated: bool = False
    # True si la zone depasse le seuil de repli : l'incremental n'est pas adapte.
    fallback_recommended: bool = False

    @property
    def impacted_job_ids(self) -> set:
        return set(self.reason_by_job)

    @property
    def nb_impacted_jobs(self) -> int:
        return len(self.reason_by_job)

    @property
    def future_job_ids(self) -> set:
        """Jobs ayant au moins une operation encore a planifier a T_now.

        Le job urgent, absent du planning courant, en fait partie : c'est bien un
        job a placer dans le futur.
        """
        jobs = set(self.state.future_job_ids)
        if self.event.event_type is PerturbationType.URGENT_JOB:
            jobs.add(self.event.payload.job_id)
        return jobs

    @property
    def nb_future_jobs(self) -> int:
        return len(self.future_job_ids)

    @property
    def ratio_future_jobs_affected(self) -> float:
        """Part des jobs futurs touches — base du garde-fou de repli (Sec. 2.6)."""
        total = self.nb_future_jobs
        if total == 0:
            return 0.0
        return len(self.impacted_job_ids & self.future_job_ids) / total

    @property
    def untouched_future_entries(self) -> list:
        """Entrees futures hors zone d'impact : le contexte droit exact, non retouche."""
        impacted = {id(e) for e in self.impacted_entries}
        return [e for e in self.state.future_entries if id(e) not in impacted]

    @property
    def machines_involved(self) -> set:
        return {e.machine_id for e in self.impacted_entries}


class ImpactAnalyzer:
    """Calcule l'ImpactZone d'un PerturbationEvent sur un Schedule donne."""

    def __init__(
        self,
        search_horizon_fraction: float = DEFAULT_SEARCH_HORIZON_FRACTION,
        max_impacted_jobs_fraction: float = DEFAULT_MAX_IMPACTED_JOBS_FRACTION,
        fallback_threshold: float = DEFAULT_FALLBACK_THRESHOLD,
        state_manager: ScheduleStateManager = None,
        search_horizon: int = None,
        max_impacted_jobs: int = None,
        min_search_horizon: int = None,
        min_impacted_jobs: int = DEFAULT_MIN_IMPACTED_JOBS,
    ):
        """
        Les deux bornes sont relatives a l'instance traitee (cf. D7 : l'unite de
        temps du projet est abstraite). Elles sont resolues a chaque `analyze()`,
        car elles dependent du planning et de T_now, pas seulement du constructeur.

        Args:
            search_horizon_fraction: part de l'horizon restant depuis T_now
                couverte par la recherche (defaut 0.15). Dans ]0, 1].
            max_impacted_jobs_fraction: part des jobs futurs admise dans la zone
                (defaut 0.20). Dans ]0, 1].
            fallback_threshold: part des jobs futurs au-dela de laquelle
                l'incremental n'est plus adapte (defaut 0.5, soit 50 %).
            state_manager: injectable, pour les tests.
            search_horizon: surcharge ABSOLUE de l'horizon, en unites de temps du
                Schedule. Court-circuite entierement la fraction et son plancher.
            max_impacted_jobs: surcharge ABSOLUE du nombre de jobs de la zone.
                Court-circuite entierement la fraction et son plancher.
            min_search_horizon: plancher absolu de l'horizon. Par defaut None :
                le plancher est alors derive du planning (la plus longue occupation
                future), donc lui aussi sans unite.
            min_impacted_jobs: plancher du nombre de jobs de la zone (defaut 2).
        """
        if not 0 < search_horizon_fraction <= 1:
            raise ValueError(
                "search_horizon_fraction doit etre dans ]0, 1], recu "
                f"{search_horizon_fraction}"
            )
        if not 0 < max_impacted_jobs_fraction <= 1:
            raise ValueError(
                "max_impacted_jobs_fraction doit etre dans ]0, 1], recu "
                f"{max_impacted_jobs_fraction}"
            )
        if not 0 < fallback_threshold <= 1:
            raise ValueError(
                f"fallback_threshold doit etre dans ]0, 1], recu {fallback_threshold}"
            )
        if search_horizon is not None and search_horizon <= 0:
            raise ValueError(f"search_horizon doit etre > 0, recu {search_horizon}")
        if max_impacted_jobs is not None and max_impacted_jobs <= 0:
            raise ValueError(f"max_impacted_jobs doit etre > 0, recu {max_impacted_jobs}")
        if min_search_horizon is not None and min_search_horizon <= 0:
            raise ValueError(
                f"min_search_horizon doit etre > 0, recu {min_search_horizon}"
            )
        if min_impacted_jobs < 1:
            raise ValueError(f"min_impacted_jobs doit etre >= 1, recu {min_impacted_jobs}")
        self.search_horizon_fraction = search_horizon_fraction
        self.max_impacted_jobs_fraction = max_impacted_jobs_fraction
        self.fallback_threshold = fallback_threshold
        self.search_horizon = search_horizon
        self.max_impacted_jobs = max_impacted_jobs
        self.min_search_horizon = min_search_horizon
        self.min_impacted_jobs = min_impacted_jobs
        self.state_manager = state_manager or ScheduleStateManager()

    # -- resolution des bornes relatives (cf. D7) ---------------------------
    def resolve_search_horizon(self, state, t_now: int) -> int:
        """Horizon de recherche effectif, en unites de temps du Schedule.

        Relatif a ce qu'il RESTE a planifier apres T_now : une meme fraction donne
        une fenetre large sur un planning long et etroite sur un planning court.
        """
        if self.search_horizon is not None:
            return self.search_horizon
        fin = max((e.end_time for e in state.future_entries), default=t_now)
        restant = max(0, fin - t_now)
        return max(int(restant * self.search_horizon_fraction),
                   self._plancher_horizon(state))

    def _plancher_horizon(self, state) -> int:
        """Plancher de l'horizon, sans unite physique.

        Par defaut la plus longue occupation future (setup compris) : en dessous,
        la fenetre ne pourrait meme pas contenir une operation entiere, et la zone
        serait systematiquement vide sur une petite instance.
        """
        if self.min_search_horizon is not None:
            return self.min_search_horizon
        return max((e.end_time - _occ_start(e) for e in state.future_entries),
                   default=1)

    def resolve_max_impacted_jobs(self, nb_future_jobs: int) -> int:
        """Nombre maximal de jobs admis dans la zone, relatif aux jobs futurs."""
        if self.max_impacted_jobs is not None:
            return self.max_impacted_jobs
        return max(int(nb_future_jobs * self.max_impacted_jobs_fraction),
                   self.min_impacted_jobs)

    # ----------------------------------------------------------------------
    def analyze(self, event, schedule, instance, t_now: int = None) -> ImpactZone:
        """Determine la zone d'impact d'un evenement sur le planning courant.

        Args:
            event: le PerturbationEvent declencheur.
            schedule: le Schedule issu de la resolution precedente.
            instance: la ProblemInstance correspondante (pour les operations des jobs).
            t_now: instant present ; par defaut `event.timestamp`.
        """
        t_now = event.timestamp if t_now is None else t_now
        state = self.state_manager.split(schedule, t_now)
        search_horizon = self.resolve_search_horizon(state, t_now)
        zone = ImpactZone(
            event=event,
            t_now=t_now,
            state=state,
            horizon_end=t_now + search_horizon,
            search_horizon=search_horizon,
        )
        # Depend de zone.nb_future_jobs, donc calcule apres la construction.
        zone.max_impacted_jobs = self.resolve_max_impacted_jobs(zone.nb_future_jobs)

        # Entrees futures indexees par machine et par job, triees par debut.
        by_machine, by_job = {}, {}
        for entry in state.future_entries:
            by_machine.setdefault(entry.machine_id, []).append(entry)
            by_job.setdefault(entry.job_id, []).append(entry)
        for entries in by_machine.values():
            entries.sort(key=_occ_start)
        for entries in by_job.values():
            entries.sort(key=lambda e: e.position_in_job)

        ctx = _Propagation(zone=zone, by_machine=by_machine, by_job=by_job,
                           analyzer=self)
        self._seed_direct_impact(event, ctx, instance)
        ctx.run()

        zone.impacted_entries = [
            e for e in state.future_entries if e.job_id in zone.reason_by_job
        ]
        zone.fallback_recommended = (
            zone.ratio_future_jobs_affected > self.fallback_threshold
        )
        if zone.fallback_recommended:
            logger.warning(
                "Zone d'impact au-dela du seuil de repli (%.0f%% > %.0f%%) : "
                "l'incremental n'est pas adapte a cette perturbation",
                100 * zone.ratio_future_jobs_affected, 100 * self.fallback_threshold,
            )
        logger.info(
            "ImpactZone: %s -> %d job(s) sur %d futurs (%.0f%%), %d entree(s)%s "
            "[horizon %d, max %d jobs]",
            event.event_type.value, zone.nb_impacted_jobs, zone.nb_future_jobs,
            100 * zone.ratio_future_jobs_affected, len(zone.impacted_entries),
            " [tronquee]" if zone.truncated else "",
            zone.search_horizon, zone.max_impacted_jobs,
        )
        return zone

    # -- garde-fou de repli (Sec. 2.6) --------------------------------------
    def is_suitable(self, zone) -> bool:
        """L'incremental a-t-il encore du sens pour cette zone ?"""
        return not zone.fallback_recommended

    def check_suitability(self, zone) -> None:
        """Leve IncrementalNotSuitableError si la zone depasse le seuil.

        A appeler entre l'analyse et la re-optimisation quand on veut un echec
        franc plutot qu'un simple drapeau. Voir IncrementalNotSuitableError pour
        le contrat attendu du futur routage.
        """
        if zone.fallback_recommended:
            raise IncrementalNotSuitableError(zone, self.fallback_threshold)

    # -- impact direct, par type d'evenement --------------------------------
    def _seed_direct_impact(self, event, ctx, instance) -> None:
        payload = event.payload
        etype = event.event_type

        if etype is PerturbationType.MACHINE_BREAKDOWN:
            # Toutes les operations futures prevues sur la machine pendant la
            # fenetre d'indisponibilite : elles doivent etre repoussees apres la
            # fin de la panne.
            for entry in ctx.by_machine.get(payload.machine_id, []):
                if _occ_start(entry) < payload.end_time and entry.end_time > payload.start_time:
                    ctx.mark(entry, REASON_DIRECT, delay=payload.end_time - _occ_start(entry))
            # Le retard se propage ensuite sur le reste de la machine.
            ctx.push_machine(payload.machine_id, after=payload.start_time,
                             delay=payload.end_time - payload.start_time)

        elif etype is PerturbationType.DURATION_CHANGE:
            entry = ctx.find_entry(payload.job_id, payload.position_in_job)
            delta = payload.new_duration - (entry.duration if entry else 0)
            ctx.mark_job(payload.job_id, REASON_DIRECT)
            if entry is not None:
                # Un allongement pousse l'aval ; un raccourcissement libere autant
                # de marge, qui peut permettre a l'aval d'avancer. Dans les deux
                # cas c'est l'amplitude du decalage qui se propage.
                ctx.propagate_from(entry, abs(delta))
            else:
                # L'operation est deja figee (en cours) : seul l'aval du job bouge.
                ctx.propagate_downstream_of_job(payload.job_id, abs(delta))

        elif etype is PerturbationType.JOB_CANCEL:
            # Les creneaux liberes permettent aux operations suivantes d'avancer.
            ctx.mark_job(payload.job_id, REASON_DIRECT)
            for entry in ctx.by_job.get(payload.job_id, []):
                libere = entry.end_time - _occ_start(entry)
                ctx.push_machine(entry.machine_id, after=_occ_start(entry), delay=libere)

        elif etype is PerturbationType.URGENT_JOB:
            # Le nouveau job n'est pas dans le planning courant : il n'a pas
            # d'entree, seulement des operations a placer. Chaque machine qu'il
            # utilise doit absorber sa duree.
            ctx.mark_job(payload.job_id, REASON_DIRECT)
            for op in payload.operations:
                ctx.push_machine(op.machine_id, after=event.timestamp, delay=op.duration)

        elif etype is PerturbationType.RESOURCE_CHANGE:
            # WR resserre : les setups de la fenetre doivent se serialiser
            # davantage. Sont concernees les operations dont le setup tombe dans
            # la fenetre, et le retard se propage machine par machine.
            for machine_id, entries in ctx.by_machine.items():
                plus_long = 0
                for entry in entries:
                    if entry.setup is None or entry.setup.duration <= 0:
                        continue
                    if (entry.setup.start_time < payload.end_time
                            and entry.setup.end_time > payload.start_time):
                        ctx.mark(entry, REASON_DIRECT, delay=entry.setup.duration)
                        plus_long = max(plus_long, entry.setup.duration)
                if plus_long:
                    ctx.push_machine(machine_id, after=payload.start_time, delay=plus_long)


def _occ_start(entry) -> int:
    """Debut d'occupation reelle de la machine : le setup precede l'operation."""
    if entry.setup and entry.setup.duration > 0:
        return min(entry.start_time, entry.setup.start_time)
    return entry.start_time


@dataclass
class _Propagation:
    """Etat de la propagation du retard : file de travail + relaxation.

    Une entree n'est retraitee que si on lui decouvre un retard STRICTEMENT plus
    grand que celui deja enregistre, ce qui garantit la terminaison.
    """

    zone: ImpactZone
    by_machine: dict
    by_job: dict
    analyzer: ImpactAnalyzer
    delays: dict = field(default_factory=dict)  # id(entry) -> retard connu
    queue: list = field(default_factory=list)

    # -- API utilisee par _seed_direct_impact -------------------------------
    def find_entry(self, job_id: str, position: int):
        for entry in self.by_job.get(job_id, []):
            if entry.position_in_job == position:
                return entry
        return None

    def mark_job(self, job_id: str, reason: str) -> None:
        if job_id in self.zone.reason_by_job:
            return
        if self._at_capacity():
            self.zone.truncated = True
            return
        self.zone.reason_by_job[job_id] = reason

    def mark(self, entry, reason: str, delay: int) -> bool:
        """Marque une entree impactee et l'empile si le retard progresse."""
        if _occ_start(entry) > self.zone.horizon_end:
            self.zone.truncated = True
            return False
        connu = self.delays.get(id(entry))
        if connu is not None and delay <= connu:
            return False
        if entry.job_id not in self.zone.reason_by_job:
            if self._at_capacity():
                self.zone.truncated = True
                return False
            self.zone.reason_by_job[entry.job_id] = reason
        self.delays[id(entry)] = delay
        self.queue.append((entry, delay))
        return True

    def push_machine(self, machine_id: str, after: int, delay: int) -> None:
        """Propage un retard sur une machine a partir d'un instant donne."""
        if delay <= 0:
            return
        restant = delay
        curseur = after
        for entry in self.by_machine.get(machine_id, []):
            debut = _occ_start(entry)
            if debut < after:
                continue
            if debut > self.zone.horizon_end:
                self.zone.truncated = True
                break
            # Le temps mort qui precede absorbe une partie du decalage.
            restant -= max(0, debut - curseur)
            if restant <= 0:
                break  # le planning a absorbe la perturbation : on s'arrete la
            self.mark(entry, REASON_CONTENTION, restant)
            curseur = entry.end_time

    def propagate_from(self, entry, delay: int) -> None:
        self.mark(entry, REASON_DIRECT, delay)
        self.run()

    def propagate_downstream_of_job(self, job_id: str, delay: int) -> None:
        for suivant in self.by_job.get(job_id, []):
            self.mark(suivant, REASON_PRECEDENCE, delay)

    # -- boucle principale ---------------------------------------------------
    def run(self) -> None:
        while self.queue:
            entry, delay = self.queue.pop()
            if self.delays.get(id(entry)) != delay:
                continue  # retard perime, une valeur plus grande a ete traitee
            # Cascade par precedence : les operations en aval du meme job.
            for suivant in self.by_job.get(entry.job_id, []):
                if suivant.position_in_job > entry.position_in_job:
                    self.mark(suivant, REASON_PRECEDENCE, delay)
            # Cascade par contention : le reste de la machine derriere cette operation.
            self.push_machine(entry.machine_id, after=entry.end_time, delay=delay)

    def _at_capacity(self) -> bool:
        # La borne est celle resolue pour CETTE analyse (relative aux jobs futurs),
        # pas un attribut fixe de l'analyzer.
        return len(self.zone.reason_by_job) >= self.zone.max_impacted_jobs
