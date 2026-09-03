"""Tests d'ImpactAnalyzer : impact direct, cascades, bornes de l'horizon."""
import pytest

from scheduling.components.impact_analyzer import (
    REASON_CONTENTION,
    REASON_DIRECT,
    REASON_PRECEDENCE,
    ImpactAnalyzer,
)
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
    """Atelier jouet, planning serre sur M1 puis aere.

    M1 : J1[100-150] J2[150-200] J3[200-250]   puis J4[400-450] (gros temps mort)
    M2 : J1[150-180] J2[200-230]
    T_now = 90 : tout est futur.
    """
    entries = [
        _entry("J1", "M1", 1, 100, 50),
        _entry("J2", "M1", 1, 150, 50),
        _entry("J3", "M1", 1, 200, 50),
        _entry("J4", "M1", 1, 400, 50),
        _entry("J1", "M2", 2, 150, 30),
        _entry("J2", "M2", 2, 200, 30),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1), Operation("J1", "M2", 30, 2)],
            deadline=300, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1), Operation("J2", "M2", 30, 2)],
            deadline=300, weight=1.0),
        Job(id="J3", operations=[Operation("J3", "M1", 50, 1)], deadline=300, weight=1.0),
        Job(id="J4", operations=[Operation("J4", "M1", 50, 1)], deadline=600, weight=1.0),
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1", "M2"], setup_times={}, wr=2)
    return Schedule(entries=entries), instance


@pytest.fixture
def analyzer():
    return ImpactAnalyzer(search_horizon=1000, max_impacted_jobs=50)


# -- panne machine ----------------------------------------------------------
def test_panne_machine_touche_les_operations_de_la_fenetre(analyzer, atelier):
    """Critere : les operations prevues sur la machine pendant la panne y sont."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = analyzer.analyze(event, schedule, instance)

    assert zone.reason_by_job["J1"] == REASON_DIRECT  # M1 100-150, dans la fenetre
    assert zone.reason_by_job["J2"] == REASON_DIRECT  # M1 150-200, chevauche la fenetre


def test_panne_machine_cascade_en_aval_par_precedence(analyzer, atelier):
    """L'operation M2 de J1 est en aval du meme job : elle suit."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = analyzer.analyze(event, schedule, instance)

    entrees_m2 = [e for e in zone.impacted_entries if e.machine_id == "M2"]
    assert {e.job_id for e in entrees_m2} == {"J1", "J2"}


def test_panne_machine_cascade_par_contention(analyzer, atelier):
    """J3 suit J2 sans temps mort sur M1 : il doit se decaler."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = analyzer.analyze(event, schedule, instance)

    assert zone.reason_by_job["J3"] == REASON_CONTENTION


def test_le_temps_mort_absorbe_le_retard(analyzer, atelier):
    """Critere : une perturbation locale et courte ne rouvre pas tout le futur.

    J4 demarre a 400, soit 150 unites de temps mort apres J3 : un retard de 60
    est integralement absorbe avant de l'atteindre.
    """
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = analyzer.analyze(event, schedule, instance)

    assert "J4" not in zone.impacted_job_ids
    assert zone.nb_impacted_jobs == 3
    assert zone.ratio_future_jobs_affected == pytest.approx(3 / 4)


def test_panne_sur_machine_inutilisee_nimpacte_rien(analyzer, atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M9", start_time=100, end_time=160)
    zone = analyzer.analyze(event, schedule, instance)
    assert zone.impacted_job_ids == set()


def test_panne_apres_lhorizon_de_recherche_ninclut_rien():
    """L'horizon borne la recherche, il n'est pas cosmetique."""
    analyzer = ImpactAnalyzer(search_horizon=5, max_impacted_jobs=50)
    entries = [_entry("J1", "M1", 1, 100, 50)]
    jobs = [Job(id="J1", operations=[Operation("J1", "M1", 50, 1)], deadline=300, weight=1.0)]
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times={}, wr=1)
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = analyzer.analyze(event, Schedule(entries=entries), instance)

    assert zone.horizon_end == 95  # 90 + 5, avant le debut de J1
    assert zone.impacted_job_ids == set()
    assert zone.truncated is True


def test_operation_demarrant_pile_sur_lhorizon_est_incluse():
    """La borne de l'horizon est inclusive (start_time <= horizon_end)."""
    analyzer = ImpactAnalyzer(search_horizon=10, max_impacted_jobs=50)
    entries = [_entry("J1", "M1", 1, 100, 50)]
    jobs = [Job(id="J1", operations=[Operation("J1", "M1", 50, 1)], deadline=300, weight=1.0)]
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times={}, wr=1)
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = analyzer.analyze(event, Schedule(entries=entries), instance)

    assert zone.horizon_end == 100
    assert zone.impacted_job_ids == {"J1"}


def test_horizon_est_configurable_pas_code_en_dur(atelier):
    """Le meme evenement donne une zone plus large avec un horizon plus large."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=400)
    court = ImpactAnalyzer(search_horizon=120, max_impacted_jobs=50)
    large = ImpactAnalyzer(search_horizon=1000, max_impacted_jobs=50)

    zone_courte = court.analyze(event, schedule, instance)
    zone_large = large.analyze(event, schedule, instance)
    assert zone_courte.impacted_job_ids < zone_large.impacted_job_ids


def test_max_impacted_jobs_borne_la_zone(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    analyzer = ImpactAnalyzer(search_horizon=1000, max_impacted_jobs=2)
    zone = analyzer.analyze(event, schedule, instance)

    assert zone.nb_impacted_jobs == 2
    assert zone.truncated is True


def test_parametres_invalides_refuses():
    with pytest.raises(ValueError, match="search_horizon"):
        ImpactAnalyzer(search_horizon=0)
    with pytest.raises(ValueError, match="max_impacted_jobs"):
        ImpactAnalyzer(max_impacted_jobs=0)


# -- operations figees ------------------------------------------------------
def test_les_operations_figees_ne_sont_jamais_dans_la_zone(analyzer, atelier):
    """T_now = 175 : J1/M1 et J2/M1 ont demarre, elles sont hors zone."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=175,
                       machine_id="M1", start_time=180, end_time=240)
    zone = analyzer.analyze(event, schedule, instance)

    figees = {(e.job_id, e.machine_id) for e in zone.state.frozen_entries}
    en_zone = {(e.job_id, e.machine_id) for e in zone.impacted_entries}
    assert figees & en_zone == set()
    assert ("J1", "M1") in figees


# -- autres types d'evenement -----------------------------------------------
def test_duration_change_cascade_en_aval_du_job_et_de_la_machine(analyzer, atelier):
    schedule, instance = atelier
    event = make_event("duration_change", timestamp=90, job_id="J1",
                       position_in_job=1, machine_id="M1", new_duration=110)
    zone = analyzer.analyze(event, schedule, instance)

    assert zone.reason_by_job["J1"] == REASON_DIRECT
    assert "J2" in zone.impacted_job_ids  # decalee sur M1
    # L'operation M2 de J1 est en aval du meme job.
    assert any(e.job_id == "J1" and e.machine_id == "M2" for e in zone.impacted_entries)


def test_duration_change_sur_operation_figee_ne_bouge_que_laval(analyzer, atelier):
    """L'operation en cours ne peut plus bouger ; son aval, si."""
    schedule, instance = atelier
    event = make_event("duration_change", timestamp=120, job_id="J1",
                       position_in_job=1, machine_id="M1", new_duration=110)
    zone = analyzer.analyze(event, schedule, instance)

    assert "J1" in zone.impacted_job_ids
    assert all(e.start_time > 120 for e in zone.impacted_entries)


def test_job_cancel_libere_des_creneaux_pour_les_suivants(analyzer, atelier):
    schedule, instance = atelier
    event = make_event("job_cancel", timestamp=90, job_id="J1")
    zone = analyzer.analyze(event, schedule, instance)

    assert zone.reason_by_job["J1"] == REASON_DIRECT
    # J2 suit J1 sur M1 : il peut avancer dans le creneau libere.
    assert "J2" in zone.impacted_job_ids


def test_urgent_job_impacte_les_machines_quil_utilise(analyzer, atelier):
    schedule, instance = atelier
    event = make_event("urgent_job", timestamp=90, job_id="J99",
                       operations=[Operation("J99", "M1", 40, 1)],
                       deadline=250, weight=9.0)
    zone = analyzer.analyze(event, schedule, instance)

    assert zone.reason_by_job["J99"] == REASON_DIRECT
    assert "J1" in zone.impacted_job_ids  # premiere operation M1 apres T_now
    assert "J99" in zone.future_job_ids   # compte comme job futur pour le ratio


def test_resource_change_impacte_les_setups_de_la_fenetre(analyzer):
    setup = SetupEntry(from_job_id="J1", start_time=140, end_time=150, duration=10)
    entries = [
        _entry("J1", "M1", 1, 100, 40),
        _entry("J2", "M1", 1, 150, 50, setup=setup),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 40, 1)], deadline=300, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1)], deadline=300, weight=1.0),
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times={}, wr=2)
    event = make_event("resource_change", timestamp=90, new_wr=1,
                       start_time=130, end_time=200)
    zone = analyzer.analyze(event, Schedule(entries=entries), instance)

    assert zone.reason_by_job["J2"] == REASON_DIRECT


# -- coherence de la zone ---------------------------------------------------
def test_zone_et_futur_non_touche_partitionnent_les_entrees_futures(analyzer, atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = analyzer.analyze(event, schedule, instance)

    reunion = zone.impacted_entries + zone.untouched_future_entries
    assert {id(e) for e in reunion} == {id(e) for e in zone.state.future_entries}
    assert len(reunion) == len(zone.state.future_entries)


def test_sur_instance_reelle_une_panne_courte_reste_locale(example_schedule, example_instance):
    """Critere d'acceptation, sur le planning a 10 jobs reellement resolu."""
    analyzer = ImpactAnalyzer(search_horizon=240, max_impacted_jobs=30)
    t_now = example_schedule.horizon // 3
    machine = example_instance.machines[0]
    event = make_event("machine_breakdown", timestamp=t_now, machine_id=machine,
                       start_time=t_now + 1, end_time=t_now + 16)
    zone = analyzer.analyze(event, example_schedule, example_instance)

    assert zone.ratio_future_jobs_affected < 1.0
    for entry in zone.impacted_entries:
        assert entry.start_time > t_now
