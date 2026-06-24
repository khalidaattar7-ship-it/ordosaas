"""Tests unitaires pour le WindowManager."""
from scheduling.components.window_manager import WindowManager
from scheduling.solvers.atcs_solver import ATCSSolver
from tests.benchmarks.taillard import generate_taillard_instance


def _atcs(instance):
    return ATCSSolver().solve(instance)


def test_single_window_for_small_instance():
    """An instance with <= max_jobs produces a single window."""
    instance = generate_taillard_instance(nb_jobs=20, nb_machines=3, seed=1)
    schedule = _atcs(instance)
    windows = WindowManager(max_jobs=50, min_jobs=5).create_windows(instance, schedule)
    assert len(windows) == 1
    assert windows[0].nb_jobs == 20


def test_multiple_windows_for_large_instance():
    """100 jobs with max_jobs=40 yields at least 2 windows."""
    instance = generate_taillard_instance(nb_jobs=100, nb_machines=3, seed=2)
    schedule = _atcs(instance)
    windows = WindowManager(max_jobs=40, min_jobs=5).create_windows(instance, schedule)
    assert len(windows) >= 2


def test_min_jobs_constraint():
    """A trailing chunk smaller than min_jobs is merged into the previous window."""
    # 85 jobs, max=40 -> chunks of 40, 40, 5. With min_jobs=10 the last (5) merges.
    instance = generate_taillard_instance(nb_jobs=85, nb_machines=2, seed=3)
    schedule = _atcs(instance)
    windows = WindowManager(max_jobs=40, min_jobs=10).create_windows(instance, schedule)
    assert all(w.nb_jobs >= 10 for w in windows), [w.nb_jobs for w in windows]


def test_window_boundaries_cover_all_jobs():
    """Every job belongs to exactly one window."""
    instance = generate_taillard_instance(nb_jobs=100, nb_machines=3, seed=4)
    schedule = _atcs(instance)
    windows = WindowManager(max_jobs=30, min_jobs=5).create_windows(instance, schedule)

    seen = []
    for w in windows:
        seen.extend(j.id for j in w.jobs)
    assert len(seen) == len(instance.jobs)
    assert set(seen) == {j.id for j in instance.jobs}
    assert len(seen) == len(set(seen)), "a job appears in more than one window"


def test_taillard_generator_has_no_setups():
    instance = generate_taillard_instance(nb_jobs=10, nb_machines=4, seed=5)
    assert instance.setup_times == {}
    # Each job visits each machine exactly once.
    for job in instance.jobs:
        machines_used = [op.machine_id for op in job.operations]
        assert sorted(machines_used) == sorted(instance.machines)
