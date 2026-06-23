"""Tests unitaires pour le CPSATSolver."""
from scheduling.models.context import BoundaryContext
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.solvers.cpsat_solver import CPSATSolver
from tests.conftest import assert_no_machine_overlap


def test_cpsat_returns_valid_schedule(small_instance):
    schedule = CPSATSolver(timeout_seconds=30).solve(small_instance)
    assert schedule is not None
    assert schedule.total_weighted_tardiness >= 0
    assert len(schedule.entries) == sum(len(j.operations) for j in small_instance.jobs)


def test_cpsat_respects_precedence_constraints(small_instance):
    schedule = CPSATSolver(timeout_seconds=30).solve(small_instance)
    jobs_ops: dict[str, list] = {}
    for entry in schedule.entries:
        jobs_ops.setdefault(entry.job_id, []).append(entry)
    for job_id, entries in jobs_ops.items():
        ordered = sorted(entries, key=lambda e: e.position_in_job)
        for k in range(len(ordered) - 1):
            assert ordered[k].end_time <= ordered[k + 1].start_time, (
                f"Precedence violated for {job_id}"
            )


def test_cpsat_no_machine_overlap(small_instance):
    schedule = CPSATSolver(timeout_seconds=30).solve(small_instance)
    assert_no_machine_overlap(schedule)


def test_cpsat_with_context():
    """solve_with_context with a non-empty left context (machine busy until t=15)."""
    jobs = [Job(id="J1", operations=[Operation("J1", "M1", 10, 1)], deadline=50, weight=1.0)]
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times={}, wr=1)
    left_ctx = BoundaryContext(
        last_job_per_machine={}, active_setups=[],
        pending_jobs=["J_prev"], machine_loads={"M1": 15},
    )
    schedule = CPSATSolver(timeout_seconds=10).solve_with_context(instance, left_ctx, None)
    assert schedule is not None
    j1_entry = next(e for e in schedule.entries if e.job_id == "J1")
    assert j1_entry.start_time >= 15


def test_cpsat_exit_context_built(small_instance):
    schedule = CPSATSolver(timeout_seconds=20).solve(small_instance)
    assert schedule.exit_context is not None
    assert set(schedule.exit_context.machine_loads.keys()) <= set(small_instance.machines)
