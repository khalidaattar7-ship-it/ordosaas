"""Tests d'integration pour le LNSRecursiveSolver."""
from scheduling.dispatcher import SolverDispatcher
from scheduling.solvers.lns_recursive import LNSRecursiveSolver
from tests.benchmarks.avgerinos import generate_avgerinos_instance


def test_lns_handles_large_instance():
    """60-job instance (> seuil_exact) goes through the 4-phase LNS."""
    instance = generate_avgerinos_instance(nb_machines=2, nb_jobs=60, seed=3)
    solver = LNSRecursiveSolver(cpsat_timeout=3, max_jobs_per_window=20)
    schedule = solver.solve(instance)
    assert schedule.method_used == "lns"
    assert len(schedule.entries) == sum(len(j.operations) for j in instance.jobs)
    assert schedule.total_weighted_tardiness >= 0
    assert schedule.atcs_twt is not None
    assert schedule.improvement_vs_atcs_pct is not None


def test_lns_progress_callback_invoked():
    instance = generate_avgerinos_instance(nb_machines=2, nb_jobs=55, seed=9)
    phases_seen = []
    solver = LNSRecursiveSolver(
        cpsat_timeout=2, max_jobs_per_window=20,
        progress_callback=lambda **kw: phases_seen.append(kw["phase"]),
    )
    solver.solve(instance)
    assert {1, 2, 3, 4}.issubset(set(phases_seen))


def test_dispatcher_routes_by_size():
    small = generate_avgerinos_instance(nb_machines=2, nb_jobs=10, seed=1)
    large = generate_avgerinos_instance(nb_machines=2, nb_jobs=60, seed=1)
    d = SolverDispatcher({"cpsat_timeout": 2, "max_jobs_per_window": 25})
    assert d.select_strategy(len(small.jobs), "auto") == "cpsat"
    assert d.select_strategy(len(large.jobs), "auto") == "lns"


def test_dispatcher_forced_atcs():
    instance = generate_avgerinos_instance(nb_machines=2, nb_jobs=12, seed=2)
    schedule = SolverDispatcher({}).dispatch(instance, "atcs")
    assert schedule.method_used == "atcs"
