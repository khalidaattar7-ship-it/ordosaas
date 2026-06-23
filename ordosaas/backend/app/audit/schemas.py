"""Pydantic schemas for the audit module."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.common import PaginationMeta


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None = None
    action: str
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    detail: dict | None = None
    ip: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    data: list[AuditLogResponse]
    pagination: PaginationMeta
