"""BoundaryContext: state propagated between temporal windows."""
from dataclasses import dataclass, field


@dataclass
class BoundaryContext:
    """Context transmitted between temporal windows."""

    # Last job processed per machine (for inter-window setups)
    last_job_per_machine: dict  # {machine_id: job_id}
    # Setups active at the boundary (for the Cumulative WR constraint)
    active_setups: list  # [(machine_id, from_job_id, to_job_id, start_time, end_time)]
    # Jobs already scheduled in previous windows (for precedences)
    pending_jobs: list  # [job_id]
    # Current load per machine (end_time of the last op)
    machine_loads: dict  # {machine_id: last_end_time}
    # Jobs straddling the boundary: some operations scheduled, some not.
    incomplete_jobs: dict = field(default_factory=dict)  # {job_id: last_completed_position}

    @classmethod
    def empty(cls) -> "BoundaryContext":
        return cls(
            last_job_per_machine={},
            active_setups=[],
            pending_jobs=[],
            machine_loads={},
            incomplete_jobs={},
        )
