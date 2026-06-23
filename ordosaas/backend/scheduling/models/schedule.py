"""Schedule result dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScheduledOperation:
    job_id: str
    op_id: str
    machine_id: str
    position: int
    start_time: int
    end_time: int
    setup_from_job: str | None = None
    setup_start_time: int | None = None
    setup_end_time: int | None = None
    setup_duration: int = 0
    window_index: int | None = None


@dataclass
class Schedule:
    entries: list = field(default_factory=list)
    windows: list = field(default_factory=list)
    method_used: str | None = None
    horizon: int = 0
    # KPIs
    total_weighted_tardiness: float = 0.0
    nb_jobs_late: int = 0
    nb_jobs_on_time: int = 0
    max_tardiness: float = 0.0
    machine_utilization_pct: float = 0.0
    total_setup_time: int = 0
    atcs_weighted_tardiness: float | None = None
    improvement_vs_atcs_pct: float | None = None
    job_completion: dict = field(default_factory=dict)
    job_tardiness: dict = field(default_factory=dict)
