"""Tests de ScheduleMerger et du validateur canonique scheduling.validation."""
import pytest

from scheduling.components.impact_analyzer import ImpactAnalyzer
from scheduling.components.incremental_context_builder import IncrementalContextBuilder
from scheduling.components.schedule_merger import ScheduleMergeError, ScheduleMerger
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.perturbation import make_event
from scheduling.models.schedule import Schedule, ScheduleEntry, SetupEntry
from scheduling.models.window import Window, WindowResult
from scheduling.solvers.incremental_optimizer import IncrementalOptimizer
from scheduling.validation import (
    ScheduleValidationError,
    assert_valid_schedule,
    find_machine_overlaps,
    find_precedence_violations,
    find_wr_violations,
    validate_schedule,
)


def _entry(job_id, machine_id, position, start, duration, setup=None):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine_id, position_in_job=position,
        start_time=start, end_time=start + duration, duration=duration, setup=setup,
    )


# ==========================================================================
# scheduling.validation : le validateur canonique
# ==========================================================================
def test_detecte_un_chevauchement_machine():
    schedule = Schedule(entries=[
        _entry("J1", "M1", 1, 0, 50),
        _entry("J2", "M1", 1, 40, 50),
    ])
    violations = find_machine_overlaps(schedule)
    assert len(violations) == 1
    assert "M1" in violations[0]


def test_deux_operations_bout_a_bout_ne_chevauchent_pas():
    schedule = Schedule(entries=[
        _entry("J1", "M1", 1, 0, 50),
        _entry("J2", "M1", 1, 50, 50),
    ])
    assert find_machine_overlaps(schedule) == []


def test_detecte_un_chevauchement_avec_un_setup():
    setup = SetupEntry(from_job_id="J1", start_time=30, end_time=60, duration=30)
    schedule = Schedule(entries=[
        _entry("J1", "M1", 1, 0, 50),          # occupe jusqu'a 50
        _entry("J2", "M1", 1, 60, 20, setup),  # son setup demarre a 30 : conflit
    ])
    assert find_machine_overlaps(schedule) != []


def test_detecte_une_violation_de_precedence():
    schedule = Schedule(entries=[
        _entry("J1", "M1", 1, 0, 50),
        _entry("J1", "M2", 2, 30, 20),  # demarre avant la fin de la position 1
    ])
    violations = find_precedence_violations(schedule)
    assert len(violations) == 1
    assert "J1" in violations[0]


def test_detecte_une_violation_de_cumulative_wr():
    """Trois setups simultanes pour WR=2."""
    entries = [
        _entry("J1", "M1", 1, 100, 10,
               SetupEntry(from_job_id="J0", start_time=90, end_time=100, duration=10)),
        _entry("J2", "M2", 1, 100, 10,
               SetupEntry(from_job_id="J0", start_time=90, end_time=100, duration=10)),
        _entry("J3", "M3", 1, 100, 10,
               SetupEntry(from_job_id="J0", start_time=90, end_time=100, duration=10)),
    ]
    violations = find_wr_violations(Schedule(entries=entries), wr=2)
    assert len(violations) == 1
    assert "WR=2" in violations[0]


def test_deux_setups_bout_a_bout_ne_sont_pas_simultanes():
    entries = [
        _entry("J1", "M1", 1, 100, 10,
               SetupEntry(from_job_id="J0", start_time=90, end_time=100, duration=10)),
        _entry("J2", "M2", 1, 110, 10,
               SetupEntry(from_job_id="J0", start_time=100, end_time=110, duration=10)),
    ]
    assert find_wr_violations(Schedule(entries=entries), wr=1) == []


def test_assert_valid_schedule_leve_sur_planning_invalide():
    schedule = Schedule(entries=[
        _entry("J1", "M1", 1, 0, 50),
        _entry("J2", "M1", 1, 40, 50),
    ])
    with pytest.raises(ScheduleValidationError, match="Chevauchement"):
        assert_valid_schedule(schedule, wr=2)


def test_le_planning_initial_du_solveur_est_valide(example_schedule, example_instance):
    """Le validateur canonique accepte ce que produit le solveur existant."""
    assert validate_schedule(example_schedule, instance=example_instance) == []


# ==========================================================================
# ScheduleMerger
# ==========================================================================
@pytest.fixture
def atelier():
    """M1 : J1[0-50] fige, J2[100-150], J3[400-450] non touche."""
    entries = [
        _entry("J1", "M1", 1, 0, 50),
        _entry("J2", "M1", 1, 100, 50),
        _entry("J2", "M2", 2, 200, 30),
        _entry("J3", "M1", 1, 400, 50),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1)], deadline=100, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1), Operation("J2", "M2", 30, 2)],
            deadline=300, weight=5.0),
        Job(id="J3", operations=[Operation("J3", "M1", 50, 1)], deadline=600, weight=1.0),
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1", "M2"], setup_times={}, wr=2)
    return Schedule(entries=entries), instance


def _chaine_complete(event, schedule, instance):
    zone = ImpactAnalyzer(search_horizon=10_000, max_impacted_jobs=50).analyze(
        event, schedule, instance
    )
    contexts = IncrementalContextBuilder().build(zone, instance)
    result = IncrementalOptimizer(timeout_seconds=10).optimize(zone, contexts, instance)
    merged, report = ScheduleMerger().merge(zone, result, instance)
    return zone, result, merged, report


def test_la_fusion_reconstitue_les_trois_segments(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone, result, merged, report = _chaine_complete(event, schedule, instance)

    attendu = (len(zone.state.frozen_entries)
               + len(result.schedule.entries)
               + len(zone.untouched_future_entries))
    assert len(merged.entries) == attendu
    assert report.nb_frozen_entries == len(zone.state.frozen_entries)
    assert report.nb_untouched_entries == len(zone.untouched_future_entries)


def test_aucune_operation_figee_nest_deplacee(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone, _, merged, _ = _chaine_complete(event, schedule, instance)

    fusionnees = {
        (e.job_id, e.position_in_job): (e.start_time, e.end_time) for e in merged.entries
    }
    for figee in zone.state.frozen_entries:
        cle = (figee.job_id, figee.position_in_job)
        assert fusionnees[cle] == (figee.start_time, figee.end_time)


def test_le_futur_non_touche_nest_pas_deplace(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone, _, merged, _ = _chaine_complete(event, schedule, instance)

    fusionnees = {
        (e.job_id, e.position_in_job): (e.start_time, e.end_time) for e in merged.entries
    }
    for intacte in zone.untouched_future_entries:
        cle = (intacte.job_id, intacte.position_in_job)
        assert fusionnees[cle] == (intacte.start_time, intacte.end_time)


def test_pas_de_chevauchement_aux_deux_frontieres(atelier):
    """Critere d'acceptation central du composant."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, _, _, report = _chaine_complete(event, schedule, instance)

    assert report.left_boundary_violations == []
    assert report.right_boundary_violations == []
    assert report.is_clean


def test_le_planning_fusionne_est_globalement_valide(atelier):
    """Memes contraintes que n'importe quel Schedule du solveur initial."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, _, merged, _ = _chaine_complete(event, schedule, instance)

    assert validate_schedule(merged, instance=instance) == []


def test_les_kpi_sont_recalcules_sur_le_planning_fusionne(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, _, merged, _ = _chaine_complete(event, schedule, instance)

    assert len(merged.jobs_result) == len(instance.jobs)
    assert merged.total_weighted_tardiness >= 0


def test_le_kpi_de_communication_compte_les_jobs_reellement_bouges(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, _, _, report = _chaine_complete(event, schedule, instance)

    assert "J2" in report.moved_job_ids  # repoussee par la panne
    assert "J1" not in report.moved_job_ids  # figee
    assert report.nb_jobs_affected == len(report.moved_job_ids)


# -- detection des frontieres invalides -------------------------------------
def test_un_chevauchement_a_la_frontiere_droite_est_detecte(atelier):
    """Zone forgee a la main qui deborde sur le futur non touche."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = ImpactAnalyzer(search_horizon=10_000, max_impacted_jobs=50).analyze(
        event, schedule, instance
    )
    # J3 non touche occupe M1 de 400 a 450 : on place la zone dessus.
    fautif = WindowResult(
        window=Window(index=0, t_start=90, t_end=430, jobs=[]),
        schedule=Schedule(entries=[_entry("J2", "M1", 1, 380, 50)]),
        exit_context=None, objective=0.0, method="incremental",
    )
    with pytest.raises(ScheduleMergeError, match="Frontiere droite"):
        ScheduleMerger().merge(zone, fautif, instance)


def test_un_chevauchement_a_la_frontiere_gauche_est_detecte(atelier):
    """Zone forgee a la main qui remonte sur une operation figee."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = ImpactAnalyzer(search_horizon=10_000, max_impacted_jobs=50).analyze(
        event, schedule, instance
    )
    # J1 fige occupe M1 de 0 a 50 : on place la zone dessus.
    fautif = WindowResult(
        window=Window(index=0, t_start=0, t_end=60, jobs=[]),
        schedule=Schedule(entries=[_entry("J2", "M1", 1, 30, 30)]),
        exit_context=None, objective=0.0, method="incremental",
    )
    with pytest.raises(ScheduleMergeError, match="Frontiere gauche"):
        ScheduleMerger().merge(zone, fautif, instance)


def test_mode_non_strict_rapporte_sans_lever(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = ImpactAnalyzer(search_horizon=10_000, max_impacted_jobs=50).analyze(
        event, schedule, instance
    )
    fautif = WindowResult(
        window=Window(index=0, t_start=0, t_end=60, jobs=[]),
        schedule=Schedule(entries=[_entry("J2", "M1", 1, 30, 30)]),
        exit_context=None, objective=0.0, method="incremental",
    )
    merged, report = ScheduleMerger().merge(zone, fautif, instance, strict=False)
    assert merged is not None
    assert not report.is_clean


# -- annulation et job urgent -----------------------------------------------
def test_job_annule_sort_des_kpi(atelier):
    schedule, instance = atelier
    event = make_event("job_cancel", timestamp=90, job_id="J2")
    _, _, merged, report = _chaine_complete(event, schedule, instance)

    assert all(r.job_id != "J2" for r in merged.jobs_result)
    assert "J2" in report.moved_job_ids


def test_job_urgent_entre_dans_les_kpi(atelier):
    schedule, instance = atelier
    event = make_event("urgent_job", timestamp=90, job_id="J99",
                       operations=[Operation("J99", "M1", 20, 1)],
                       deadline=200, weight=9.0)
    _, _, merged, _ = _chaine_complete(event, schedule, instance)

    assert any(r.job_id == "J99" for r in merged.jobs_result)
