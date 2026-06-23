"""Scheduling domain models: Operation, Job, ProblemInstance."""
from dataclasses import dataclass


@dataclass
class Operation:
    job_id: str
    machine_id: str
    duration: int
    position: int  # 1-indexed


@dataclass
class Job:
    id: str  # external_id (ex: "J1")
    operations: list  # list[Operation], ordered by position
    deadline: int
    weight: float


@dataclass
class ProblemInstance:
    jobs: list  # list[Job]
    machines: list  # external_ids of machines
    setup_times: dict  # {(from_job_id, to_job_id, machine_id): duration}
    wr: int  # nb of simultaneous setup technicians

    def get_setup(self, from_job: str, to_job: str, machine: str) -> int:
        return self.setup_times.get((from_job, to_job, machine), 0)

    @property
    def horizon(self) -> int:
        """Maximum time horizon (sum of all durations + all setups)."""
        return (
            sum(op.duration for job in self.jobs for op in job.operations)
            + sum(self.setup_times.values())
        )
