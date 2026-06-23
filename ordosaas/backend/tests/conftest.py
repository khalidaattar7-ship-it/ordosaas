"""Shared pytest fixtures for the scheduling test-suite."""
import pytest

from scheduling.models.job import Job, Operation, ProblemInstance


@pytest.fixture
def small_instance() -> ProblemInstance:
    """3 jobs x 2 machines reference instance."""
    jobs = [
        Job(id="J1", operations=[
            Operation("J1", "M1", 30, 1),
            Operation("J1", "M2", 20, 2),
        ], deadline=120, weight=8.5),
        Job(id="J2", operations=[
            Operation("J2", "M2", 25, 1),
            Operation("J2", "M1", 18, 2),
        ], deadline=95, weight=3.0),
        Job(id="J3", operations=[
            Operation("J3", "M1", 22, 1),
            Operation("J3", "M2", 12, 2),
        ], deadline=150, weight=5.0),
    ]
    setup_times = {
        ("J1", "J2", "M1"): 8, ("J2", "J1", "M1"): 6,
        ("J1", "J3", "M1"): 5, ("J3", "J1", "M1"): 7,
        ("J2", "J3", "M1"): 4, ("J3", "J2", "M1"): 9,
        ("J1", "J2", "M2"): 5, ("J2", "J1", "M2"): 3,
        ("J1", "J3", "M2"): 6, ("J3", "J1", "M2"): 4,
        ("J2", "J3", "M2"): 7, ("J3", "J2", "M2"): 5,
    }
    return ProblemInstance(jobs=jobs, machines=["M1", "M2"], setup_times=setup_times, wr=1)


def assert_no_machine_overlap(schedule):
    """Helper: assert no two intervals overlap on any machine (ops + setups)."""
    from collections import defaultdict

    slots = defaultdict(list)
    for entry in schedule.entries:
        slots[entry.machine_id].append((entry.start_time, entry.end_time))
        if entry.setup and entry.setup.duration > 0:
            slots[entry.machine_id].append((entry.setup.start_time, entry.setup.end_time))
    for machine, intervals in slots.items():
        intervals.sort()
        for i in range(len(intervals) - 1):
            assert intervals[i][1] <= intervals[i + 1][0], (
                f"Overlap on {machine}: {intervals[i]} and {intervals[i + 1]}"
            )
