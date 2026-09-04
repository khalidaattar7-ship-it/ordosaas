"""Tests de `resolve_incremental` : l'orchestrateur public de la cascade.

Ce module teste le CHAINAGE — l'ordre des six composants, la propagation de la
configuration, la gestion des cas limites — et non la logique de chaque composant,
couverte par son propre fichier de tests.
"""
import pytest

from scheduling.components.impact_analyzer import IncrementalNotSuitableError
from scheduling.components.schedule_merger import ScheduleMergeError
from scheduling.incremental import (
    IncrementalConfig,
    IncrementalResolution,
    IncrementalResolutionError,
    resolve_incremental,
)
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.perturbation import make_event
from scheduling.models.schedule import Schedule, ScheduleEntry
from scheduling.validation import validate_schedule


def _entry(job_id, machine_id, position, start, duration, setup=None):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine_id, position_in_job=position,
        start_time=start, end_time=start + duration, duration=duration, setup=setup,
    )


@pytest.fixture
def atelier():
    """M1 : J1[0-50] figé a T_now=90, puis J2[100-150] et J3[200-250] futurs."""
    entries = [
        _entry("J1", "M1", 1, 0, 50),
        _entry("J2", "M1", 1, 100, 50),
        _entry("J3", "M1", 1, 200, 50),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1)], deadline=100, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1)], deadline=400, weight=1.0),
        Job(id="J3", operations=[Operation("J3", "M1", 50, 1)], deadline=400, weight=1.0),
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times={}, wr=1)
    return Schedule(entries=entries), instance


def _panne(t_now=90):
    return make_event("machine_breakdown", timestamp=t_now,
                      machine_id="M1", start_time=100, end_time=160)


# -- chainage ---------------------------------------------------------------
def test_la_cascade_produit_un_planning_complet_et_valide(atelier):
    """Le resultat couvre tout le planning, pas seulement la zone reoptimisee."""
    schedule, instance = atelier
    resolution = resolve_incremental(schedule, _panne(), instance)

    assert isinstance(resolution, IncrementalResolution)
    assert validate_schedule(resolution.schedule, instance=instance) == []
    # Fige + zone + futur non touche : aucune operation ne disparait.
    positions = {(e.job_id, e.position_in_job) for e in resolution.schedule.entries}
    assert positions == {("J1", 1), ("J2", 1), ("J3", 1)}


def test_la_cascade_expose_letat_intermediaire(atelier):
    """Le worker et l'endpoint de diff ont besoin d'autre chose que du Schedule."""
    schedule, instance = atelier
    resolution = resolve_incremental(schedule, _panne(), instance)

    assert resolution.zone is not None
    assert resolution.window_result is not None
    assert resolution.report is not None
    assert resolution.nb_jobs_affected == resolution.report.nb_jobs_affected
    assert resolution.nb_future_jobs == resolution.zone.nb_future_jobs
    assert resolution.is_clean is resolution.report.is_clean


def test_loperation_figee_nest_jamais_touchee(atelier):
    """L'invariant central de tout l'incremental, verifie au niveau du chainage."""
    schedule, instance = atelier
    resolution = resolve_incremental(schedule, _panne(), instance)

    figee = next(e for e in resolution.schedule.entries if e.job_id == "J1")
    assert (figee.start_time, figee.end_time) == (0, 50)


def test_t_now_par_defaut_est_le_timestamp_de_levenement(atelier):
    """Ne pas passer t_now revient a le prendre sur l'evenement."""
    schedule, instance = atelier
    event = _panne(t_now=90)

    implicite = resolve_incremental(schedule, event, instance)
    explicite = resolve_incremental(schedule, event, instance, t_now=90)
    assert implicite.zone.t_now == explicite.zone.t_now == 90


def test_t_now_explicite_prime_sur_le_timestamp(atelier):
    """Le worker peut rejouer un evenement a un instant present different."""
    schedule, instance = atelier
    resolution = resolve_incremental(schedule, _panne(t_now=90), instance, t_now=120)
    assert resolution.zone.t_now == 120
    # A T_now = 120, J2 a demarre : elle est figee, plus une variable.
    figee = next(e for e in resolution.schedule.entries if e.job_id == "J2")
    assert figee.start_time == 100


# -- configuration ----------------------------------------------------------
def test_la_config_est_bien_propagee_a_lanalyzer(atelier):
    """Une surcharge absolue de l'horizon se retrouve sur la zone produite."""
    schedule, instance = atelier
    resolution = resolve_incremental(
        schedule, _panne(), instance,
        config=IncrementalConfig(search_horizon=777, max_impacted_jobs=3),
    )
    assert resolution.zone.search_horizon == 777
    assert resolution.zone.max_impacted_jobs == 3


def test_sans_config_les_defauts_des_composants_sappliquent(atelier):
    """IncrementalConfig ne redefinit aucune politique : elle regroupe des reglages.

    Un `None` dans la config signifie "garder le defaut du composant", et non
    "passer None" — les fractions et les seuils n'accepteraient pas None.
    """
    schedule, instance = atelier
    analyzer = IncrementalConfig().build_analyzer()
    assert analyzer.search_horizon_fraction == 0.15
    assert analyzer.max_impacted_jobs_fraction == 0.20
    assert analyzer.fallback_threshold == 0.5
    assert analyzer.search_horizon is None


def test_le_poids_de_stabilite_est_propage_a_loptimiseur(atelier):
    schedule, instance = atelier
    optimizer = IncrementalConfig(stability_weight=0.0).build_optimizer()
    assert optimizer.stability_weight == 0.0


# -- garde-fou de repli (H5 : signale, ne route pas) -------------------------
def test_le_repli_est_signale_mais_la_cascade_poursuit(atelier):
    """Comportement par defaut : un drapeau, pas un echec ni un routage.

    Le routage reel vers LNSRecursiveSolver reste hors perimetre (H5) : la cascade
    doit donc rester exploitable meme au-dela du seuil, et laisser l'appelant maitre.
    """
    schedule, instance = atelier
    resolution = resolve_incremental(
        schedule, _panne(), instance,
        config=IncrementalConfig(fallback_threshold=0.01, search_horizon=10_000,
                                 max_impacted_jobs=50),
    )
    assert resolution.fallback_recommended is True
    assert validate_schedule(resolution.schedule, instance=instance) == []


def test_raise_on_fallback_donne_un_echec_franc(atelier):
    """L'appelant qui prefere un echec explicite peut le demander."""
    schedule, instance = atelier
    with pytest.raises(IncrementalNotSuitableError):
        resolve_incremental(
            schedule, _panne(), instance,
            config=IncrementalConfig(fallback_threshold=0.01, raise_on_fallback=True,
                                     search_horizon=10_000, max_impacted_jobs=50),
        )


def test_le_repli_nest_pas_signale_sur_une_perturbation_locale(atelier):
    schedule, instance = atelier
    resolution = resolve_incremental(
        schedule, _panne(), instance,
        config=IncrementalConfig(fallback_threshold=1.0),
    )
    assert resolution.fallback_recommended is False


# -- cas limites ------------------------------------------------------------
def test_une_zone_sans_solution_leve_une_erreur_explicite(atelier):
    """Pas de retour None silencieux : le worker doit pouvoir marquer `failed`.

    La panne couvre tout l'horizon utile de la machine et la zone ne peut pas s'y
    replier, CP-SAT ne trouve donc aucune solution.
    """
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90, machine_id="M1",
                       start_time=100, end_time=10_000)
    with pytest.raises(IncrementalResolutionError, match="Aucune solution"):
        resolve_incremental(
            schedule, event, instance,
            config=IncrementalConfig(search_horizon=10_000, max_impacted_jobs=50,
                                     timeout_seconds=5),
        )


def test_strict_merge_est_desactivable(atelier):
    """`strict=False` renvoie le planning et laisse les violations dans le rapport."""
    schedule, instance = atelier
    resolution = resolve_incremental(
        schedule, _panne(), instance, config=IncrementalConfig(strict_merge=False),
    )
    assert resolution.schedule is not None
    assert resolution.report is not None


def test_une_perturbation_sans_impact_ne_casse_pas_la_cascade(atelier):
    """Une panne sur une machine inexistante ne touche rien, mais doit aboutir."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90, machine_id="M9",
                       start_time=100, end_time=160)
    resolution = resolve_incremental(schedule, event, instance)

    assert resolution.zone.nb_impacted_jobs == 0
    assert resolution.nb_jobs_affected == 0
    assert validate_schedule(resolution.schedule, instance=instance) == []
    # Le planning ressort identique a l'original.
    avant = {(e.job_id, e.start_time, e.end_time) for e in schedule.entries}
    apres = {(e.job_id, e.start_time, e.end_time) for e in resolution.schedule.entries}
    assert apres == avant


# -- coherence avec l'appel direct des composants ----------------------------
def test_lorchestrateur_donne_le_meme_resultat_que_la_chaine_manuelle(atelier):
    """L'orchestrateur n'ajoute aucune politique : c'est le meme chemin de code.

    C'est ce qui autorise les scenarios de tests a passer par lui plutot que par un
    enchainement local, et garantit que le worker de la Discussion 3 verra le meme
    comportement.
    """
    from scheduling.components.impact_analyzer import ImpactAnalyzer
    from scheduling.components.incremental_context_builder import (
        IncrementalContextBuilder,
    )
    from scheduling.components.schedule_merger import ScheduleMerger
    from scheduling.solvers.incremental_optimizer import IncrementalOptimizer

    schedule, instance = atelier
    event = _panne()

    zone = ImpactAnalyzer(search_horizon=1000, max_impacted_jobs=50).analyze(
        event, schedule, instance, t_now=90
    )
    contexts = IncrementalContextBuilder().build(zone, instance)
    result = IncrementalOptimizer(timeout_seconds=10).optimize(zone, contexts, instance)
    attendu, _ = ScheduleMerger().merge(zone, result, instance)

    obtenu = resolve_incremental(
        schedule, event, instance,
        config=IncrementalConfig(search_horizon=1000, max_impacted_jobs=50,
                                 timeout_seconds=10),
    ).schedule

    assert (
        sorted((e.job_id, e.position_in_job, e.start_time, e.end_time)
               for e in obtenu.entries)
        == sorted((e.job_id, e.position_in_job, e.start_time, e.end_time)
                  for e in attendu.entries)
    )
