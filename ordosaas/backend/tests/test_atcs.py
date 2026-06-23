"""Tests unitaires pour l'ATCSSolver."""
from scheduling.solvers.atcs_solver import ATCSSolver
from tests.benchmarks.avgerinos import generate_avgerinos_instance
from tests.conftest import assert_no_machine_overlap


def test_atcs_returns_valid_schedule(small_instance):
    schedule = ATCSSolver().solve(small_instance)
    assert schedule.method_used == "atcs"
    assert len(schedule.entries) == sum(len(j.operations) for j in small_instance.jobs)


def test_atcs_kpis_non_negative(small_instance):
    schedule = ATCSSolver().solve(small_instance)
    assert schedule.total_weighted_tardiness >= 0
    for jr in schedule.jobs_result:
        assert jr.tardiness >= 0
        assert jr.weighted_tardiness >= 0
        assert jr.is_late == (jr.tardiness > 0)


def test_atcs_no_machine_overlap(small_instance):
    schedule = ATCSSolver().solve(small_instance)
    assert_no_machine_overlap(schedule)


def test_atcs_precedence(small_instance):
    schedule = ATCSSolver().solve(small_instance)
    by_job: dict[str, list] = {}
    for e in schedule.entries:
        by_job.setdefault(e.job_id, []).append(e)
    for entries in by_job.values():
        ordered = sorted(entries, key=lambda e: e.position_in_job)
        for k in range(len(ordered) - 1):
            assert ordered[k].end_time <= ordered[k + 1].start_time


def test_atcs_scales_on_benchmark():
    instance = generate_avgerinos_instance(nb_machines=5, nb_jobs=50, seed=7)
    schedule = ATCSSolver().solve(instance)
    assert len(schedule.entries) == sum(len(j.operations) for j in instance.jobs)
    assert schedule.total_weighted_tardiness >= 0
