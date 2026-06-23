"""Pydantic schemas for the instances module."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.common import PaginationMeta, UserSummary


# --- CSV row schemas ---
class JobCSVRow(BaseModel):
    job_id: str
    deadline: int = Field(gt=0)
    weight: float = Field(gt=0)


class OperationCSVRow(BaseModel):
    job_id: str
    machine_id: str
    duration: int = Field(gt=0)
    position: int = Field(ge=1)


class SetupCSVRow(BaseModel):
    from_job: str
    to_job: str
    machine_id: str
    duration: int = Field(ge=0)


# --- Responses ---
class ValidationWarning(BaseModel):
    code: str
    message: str
    affected_jobs: list[str] = []


class InstanceResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    nb_jobs: int
    nb_machines: int
    nb_operations: int
    nb_setups: int
    status: str
    import_source: str
    nb_resolutions: int = 0
    best_resolution_id: uuid.UUID | None = None
    best_weighted_tardiness: float | None = None
    created_by: UserSummary | None = None
    created_at: datetime
    updated_at: datetime


class InstanceListResponse(BaseModel):
    data: list[InstanceResponse]
    pagination: PaginationMeta


class ImportResponse(BaseModel):
    id: uuid.UUID
    name: str
    nb_jobs: int
    nb_machines: int
    nb_operations: int
    nb_setups: int
    status: str
    validation_warnings: list[ValidationWarning] = []
    created_at: datetime


class JobResponse(BaseModel):
    id: uuid.UUID
    external_id: str
    deadline: int
    weight: float
    nb_operations: int
    machines: list[str] = []


class JobListResponse(BaseModel):
    data: list[JobResponse]
    pagination: PaginationMeta


class PatchJobRequest(BaseModel):
    deadline: int | None = Field(default=None, gt=0)
    weight: float | None = Field(default=None, gt=0)


class OperationInJob(BaseModel):
    machine_id: uuid.UUID
    duration: int = Field(gt=0)
    position: int = Field(ge=1)


class AddJobRequest(BaseModel):
    external_id: str
    deadline: int = Field(gt=0)
    weight: float = Field(gt=0)
    operations: list[OperationInJob]
