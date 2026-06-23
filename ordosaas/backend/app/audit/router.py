"""Audit API router."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.audit import service
from app.audit.schemas import AuditLogListResponse
from app.dependencies import CurrentUser, DbSession, require_admin

router = APIRouter()


@router.get("", response_model=AuditLogListResponse, dependencies=[Depends(require_admin)])
async def list_audit_logs(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user_id: uuid.UUID | None = None,
    action: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
):
    return await service.list_logs(
        current_user.tenant_id, page, per_page, user_id, action, from_date, to_date, db
    )
