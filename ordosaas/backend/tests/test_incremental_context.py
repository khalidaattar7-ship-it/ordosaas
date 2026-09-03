"""Tests d'IncrementalContextBuilder : les deux contextes sont exacts."""
import pytest

from scheduling.components.impact_analyzer import ImpactAnalyzer
from scheduling.components.incremental_context_builder import IncrementalContextBuilder
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.perturbation import make_event
from scheduling.models.schedule import Schedule, ScheduleEntry, SetupEntry


def _entry(job_id, machine_id, position, start, duration, setup=None):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine_id, position_in_job=position,
        start_time=start, end_time=start + duration, duration=duration, setup=setup,
    )


@pytest.fixture
def atelier():
    """M1 : J1[0-50] fige, J2[100-150] impacte, J3[400-450] non touche.

    M2 : J1[60-90] fige, J2[160-190] impacte.
    T_now = 95.
    """
    entries = [
        _entry("J1", "M1", 1, 0, 50),
        _entry("J1", "M2", 2, 60, 30),
        _entry("J2", "M1", 1, 100, 50),
        _entry("J2", "M2", 2, 160, 30),
        _entry("J3", "M1", 1, 400, 50),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1), Operation("J1", "M2", 30, 2)],
            deadline=200, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1), Operation("J2", "M2", 30, 2)],
            deadline=300, weight=1.0),
        Job(id="J3", operations=[Operation("J3", "M1", 50, 1)], deadline=600, weight=1.0),
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1", "M2"], setup_times={}, wr=2)
    return Schedule(entries=entries), instance


@pytest.fixture
def zone(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=95,
                       machine_id="M1", start_time=100, end_time=130)
    analyzer = ImpactAnalyzer(search_horizon=1000, max_impacted_jobs=50)
    return analyzer.analyze(event, schedule, instance)


@pytest.fixture
def builder():
    return IncrementalContextBuilder()


# -- les deux contextes sont exacts -----------------------------------------
def test_les_deux_contextes_sont_declares_exacts(builder, zone, atelier):
    """Critere : contrairement au LNS initial, le contexte droit n'est pas approximatif."""
    _, instance = atelier
    contexts = builder.build(zone, instance)
    assert contexts.left_is_exact is True
    assert contexts.right_is_exact is True


# -- contexte gauche --------------------------------------------------------
def test_contexte_gauche_reflete_letat_fige(builder, zone, atelier):
    _, instance = atelier
    left = builder.build_left_context(zone, instance)

    assert left.machine_loads == {"M1": 50, "M2": 90}
    assert left.last_job_per_machine == {"M1": "J1", "M2": "J1"}
    assert left.pending_jobs == ["J1"]


def test_contexte_gauche_ignore_les_entrees_futures(builder, zone, atelier):
    """J2 et J3 sont futurs : ils ne doivent pas peser sur la charge machine."""
    _, instance = atelier
    left = builder.build_left_context(zone, instance)
    assert left.machine_loads["M1"] == 50  # et non 150 ni 450


def test_contexte_gauche_signale_les_jobs_a_cheval(builder, atelier):
    """J1 a une operation figee et une future : incomplete_jobs le signale."""
    schedule, instance = atelier
    # T_now = 70 : J1/M1 fige, J1/M2 en cours (donc fige aussi) -> J1 complet.
    # On decale a T_now = 40 : seule J1/M1 a demarre, J1/M2 reste a placer.
    event = make_event("machine_breakdown", timestamp=40,
                       machine_id="M1", start_time=100, end_time=130)
    analyzer = ImpactAnalyzer(search_horizon=1000, max_impacted_jobs=50)
    zone_40 = analyzer.analyze(event, schedule, instance)
    left = IncrementalContextBuilder().build_left_context(zone_40, instance)

    assert left.incomplete_jobs == {"J1": 1}  # derniere position figee du job J1


def test_contexte_gauche_porte_les_setups_actifs(builder, atelier):
    """Un setup fige chevauchant T_now consomme encore un technicien."""
    schedule, instance = atelier
    setup = SetupEntry(from_job_id="J1", start_time=90, end_time=100, duration=10)
    schedule.entries.append(
        _entry("J3", "M2", 1, 92, 20, setup=setup)  # start 92 <= T_now=95 -> fige
    )
    event = make_event("machine_breakdown", timestamp=95,
                       machine_id="M1", start_time=100, end_time=130)
    analyzer = ImpactAnalyzer(search_horizon=1000, max_impacted_jobs=50)
    zone_95 = analyzer.analyze(event, schedule, instance)
    left = builder.build_left_context(zone_95, instance)

    assert left.active_setups == [("M2", "J1", "J3", 90, 100)]


def test_setup_fige_deja_termine_nest_pas_actif(builder, zone, atelier):
    _, instance = atelier
    left = builder.build_left_context(zone, instance)
    assert left.active_setups == []


# -- contexte droit ---------------------------------------------------------
def test_contexte_droit_borne_la_zone_par_machine(builder, zone, atelier):
    """machine_loads = date au plus tard : debut de la premiere entree non touchee."""
    _, instance = atelier
    right = builder.build_right_context(zone, instance)
    assert right.machine_loads == {"M1": 400}  # J3, seule entree future non touchee


def test_contexte_droit_nomme_la_premiere_operation_de_chaque_machine(builder, zone, atelier):
    _, instance = atelier
    right = builder.build_right_context(zone, instance)
    assert right.last_job_per_machine == {"M1": "J3"}


def test_contexte_droit_vide_quand_toute_la_suite_est_impactee(builder, atelier):
    """Sans entree non touchee, le contexte droit n'impose aucune borne."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=95,
                       machine_id="M1", start_time=100, end_time=600)
    analyzer = ImpactAnalyzer(search_horizon=10_000, max_impacted_jobs=50)
    zone_large = analyzer.analyze(event, schedule, instance)
    right = builder.build_right_context(zone_large, instance)

    assert right.machine_loads == {}
    assert right.last_job_per_machine == {}


def test_contexte_droit_vient_du_planning_optimise_pas_dune_approximation(
    builder, zone, atelier
):
    """Les bornes du contexte droit sont exactement celles du Schedule d'origine."""
    schedule, instance = atelier
    right = builder.build_right_context(zone, instance)
    for machine_id, borne in right.machine_loads.items():
        entrees = [
            e for e in zone.untouched_future_entries if e.machine_id == machine_id
        ]
        assert borne == min(e.start_time for e in entrees)


# -- sur l'instance reelle --------------------------------------------------
def test_contextes_coherents_sur_instance_reelle(example_schedule, example_instance):
    t_now = example_schedule.horizon // 3
    event = make_event("machine_breakdown", timestamp=t_now,
                       machine_id=example_instance.machines[0],
                       start_time=t_now + 1, end_time=t_now + 21)
    zone = ImpactAnalyzer(search_horizon=240, max_impacted_jobs=30).analyze(
        event, example_schedule, example_instance
    )
    contexts = IncrementalContextBuilder().build(zone, example_instance)

    # Le contexte gauche ne depasse jamais la fin des operations figees.
    fins_figees = zone.state.last_frozen_end_per_machine()
    for machine_id, charge in contexts.left.machine_loads.items():
        assert charge <= fins_figees[machine_id]
    # Toute borne droite est posterieure a T_now : elle delimite bien du futur.
    for borne in contexts.right.machine_loads.values():
        assert borne > t_now
