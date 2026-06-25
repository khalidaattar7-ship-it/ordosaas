"""Scheduling result models: SetupEntry, ScheduleEntry, JobResult, Schedule."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SetupEntry:
    from_job_id: str
    start_time: int
    end_time: int
    duration: int


@dataclass
class ScheduleEntry:
    job_id: str
    machine_id: str
    position_in_job: int
    start_time: int
    end_time: int
    duration: int
    setup: Optional[SetupEntry] = None


@dataclass
class JobResult:
    job_id: str
    deadline: int
    weight: float
    completion_time: int
    tardiness: int
    is_late: bool
    weighted_tardiness: float


@dataclass
class Schedule:
    entries: list = field(default_factory=list)
    jobs_result: list = field(default_factory=list)
    total_weighted_tardiness: float = 0.0
    method_used: str = "unknown"
    # Solver outcome status ('optimal' / 'feasible' / ...), distinct from the
    # solver that produced it (method_used). Kept separate so method_used always
    # holds the solver name (cpsat/lns/atcs) expected by the DB constraint.
    solver_status: Optional[str] = None
    # Optional KPIs / context attached by solvers
    atcs_twt: Optional[float] = None
    improvement_vs_atcs_pct: Optional[float] = None
    exit_context: object = None

    def add_entry(self, entry: ScheduleEntry):
        self.entries.append(entry)

    def compute_kpis(self, jobs: list) -> None:
        """Compute completion times and tardiness for each job from entries."""
        completions: dict[str, int] = {}
        for job in jobs:
            last_op = max(job.operations, key=lambda o: o.position)
            ends = [
                e.end_time for e in self.entries
                if e.job_id == job.id and e.machine_id == last_op.machine_id
            ]
            completions[job.id] = max(ends) if ends else 0

        self.jobs_result = []
        total = 0.0
        for job in jobs:
            completion = completions.get(job.id, 0)
            tardiness = max(0, completion - job.deadline)
            wt = round(job.weight * tardiness, 4)
            total += wt
            self.jobs_result.append(JobResult(
                job_id=job.id, deadline=job.deadline, weight=job.weight,
                completion_time=completion, tardiness=tardiness,
                is_late=tardiness > 0, weighted_tardiness=wt,
            ))
        self.total_weighted_tardiness = round(total, 4)

    # -- derived KPIs used by the API persistence layer --------------------
    @property
    def nb_jobs_late(self) -> int:
        return sum(1 for r in self.jobs_result if r.is_late)

    @property
    def nb_jobs_on_time(self) -> int:
        return sum(1 for r in self.jobs_result if not r.is_late)

    @property
    def max_tardiness(self) -> int:
        return max((r.tardiness for r in self.jobs_result), default=0)

    @property
    def total_setup_time(self) -> int:
        return sum(e.setup.duration for e in self.entries if e.setup)

    @property
    def horizon(self) -> int:
        return max((e.end_time for e in self.entries), default=0)

    def machine_utilization_pct(self, machines: list) -> float:
        horizon = self.horizon
        if not machines or horizon <= 0:
            return 0.0
        busy = sum(e.duration for e in self.entries)
        return round(100.0 * busy / (horizon * len(machines)), 2)
