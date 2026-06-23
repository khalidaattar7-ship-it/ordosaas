"""Pydantic schemas for the comparisons module."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class CompareRequest(BaseModel):
    resolution_a_id: uuid.UUID
    resolution_b_id: uuid.UUID


class ResolutionSummary(BaseModel):
    id: uuid.UUID
    method_used: str | None = None
    total_weighted_tardiness: float | None = None
    nb_jobs_late: int | None = None
    machine_utilization_pct: float | None = None
    total_setup_time: int | None = None


class DeltaSummary(BaseModel):
    delta_weighted_tardiness: float | None = None
    delta_jobs_late: int | None = None
    delta_machine_utilization: float | None = None
    delta_setup_time: int | None = None


class JobDelta(BaseModel):
    external_id: str
    tardiness_a: float | None = None
    tardiness_b: float | None = None
    delta: float | None = None


class ComparisonResponse(BaseModel):
    id: uuid.UUID
    resolution_a: ResolutionSummary
    resolution_b: ResolutionSummary
    delta: DeltaSummary
    winner: str | None = None
    changed_jobs: list[JobDelta] = []
    created_at: datetime
