"""Pydantic schemas for the resolutions module."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class ResolveRequest(BaseModel):
    wr: int = 5
    strategy: str = "auto"
    cpsat_timeout: int = 30
    max_jobs_per_window: int = 50
    min_jobs_per_window: int = 5
    max_recursion_depth: int = 4
    max_iterations: int = 5
    epsilon: float = 0.01
    junction_radius: int = 10
    k1: float | None = None
    k2: float | None = None


class ResolveResponse(BaseModel):
    resolution_id: uuid.UUID
    instance_id: uuid.UUID
    status: str
    estimated_duration_seconds: int
    strategy_selected: str
    created_at: datetime


class KPIs(BaseModel):
    total_weighted_tardiness: float | None = None
    nb_jobs_late: int | None = None
    nb_jobs_on_time: int | None = None
    max_tardiness: float | None = None
    machine_utilization_pct: float | None = None
    total_setup_time: int | None = None
    atcs_weighted_tardiness: float | None = None
    improvement_vs_atcs_pct: float | None = None


class ResolutionStatus(BaseModel):
    id: uuid.UUID
    instance_id: uuid.UUID
    status: str
    progress_pct: int
    current_phase: int
    progress_detail: dict | None = None
    method_used: str | None = None
    kpis: KPIs | None = None
    duration_seconds: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class SetupInfo(BaseModel):
    from_job_id: uuid.UUID
    from_job_external_id: str
    start_time: int
    end_time: int
    duration: int


class GanttEntry(BaseModel):
    job_id: uuid.UUID
    job_external_id: str
    job_deadline: int
    job_weight: float
    job_tardiness: float | None = None
    job_completion_time: int | None = None
    is_late: bool
    machine_id: uuid.UUID
    machine_external_id: str
    start_time: int
    end_time: int
    duration: int
    position_in_job: int
    window_index: int | None = None
    setup: SetupInfo | None = None


class MachineSummary(BaseModel):
    id: uuid.UUID
    external_id: str
    name: str


class WindowSummary(BaseModel):
    window_index: int
    t_start: int
    t_end: int
    nb_jobs: int
    status: str
    method_used: str | None = None


class GanttResponse(BaseModel):
    resolution_id: uuid.UUID
    horizon: int
    kpis: KPIs
    machines: list[MachineSummary]
    windows: list[WindowSummary]
    entries: list[GanttEntry]


class OperationInSchedule(BaseModel):
    position: int
    machine_external_id: str
    start_time: int
    end_time: int
    duration: int
    setup_from_job: str | None = None
    setup_duration: int = 0


class JobDetailInResolution(BaseModel):
    job_id: uuid.UUID
    external_id: str
    deadline: int
    weight: float
    completion_time: int | None = None
    tardiness: float | None = None
    is_late: bool
    weighted_tardiness: float | None = None
    window_index: int | None = None
    window_status: str | None = None
    operations: list[OperationInSchedule] = []
