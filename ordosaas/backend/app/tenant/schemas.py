"""Pydantic schemas for the tenant module."""
import uuid
from typing import Literal

from pydantic import BaseModel


class TenantLimits(BaseModel):
    max_jobs_per_instance: int
    max_machines_per_instance: int
    max_instances_stored: int


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    default_wr: int
    default_timeout: int
    default_strategy: str
    timezone: str
    limits: TenantLimits


class PatchTenantRequest(BaseModel):
    name: str | None = None
    default_wr: int | None = None
    default_timeout: int | None = None
    default_strategy: Literal["auto", "cpsat", "lns", "atcs"] | None = None
    timezone: str | None = None
