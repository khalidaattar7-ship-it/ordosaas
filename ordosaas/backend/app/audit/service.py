"""Audit logging business logic."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import AuditLogListResponse, AuditLogResponse
from app.common import paginate_meta
from app.models.audit_log import AuditLog


async def log_action(
    tenant_id, user_id, action, resource_type=None, resource_id=None,
    detail=None, ip=None, db: AsyncSession = None,
) -> None:
    """Record an audit entry. Best-effort: never raises to the caller."""
    if db is None:
        return
    entry = AuditLog(
        tenant_id=tenant_id, user_id=user_id, action=action,
        resource_type=resource_type, resource_id=resource_id,
        detail=detail, ip=ip,
    )
    db.add(entry)
    await db.commit()
    return None


async def list_logs(
    tenant_id, page, per_page, user_id=None, action=None,
    from_date: datetime | None = None, to_date: datetime | None = None,
    db: AsyncSession = None,
) -> AuditLogListResponse:
    filters = [AuditLog.tenant_id == tenant_id]
    if user_id:
        filters.append(AuditLog.user_id == user_id)
    if action:
        filters.append(AuditLog.action == action)
    if from_date:
        filters.append(AuditLog.created_at >= from_date)
    if to_date:
        filters.append(AuditLog.created_at <= to_date)

    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*filters))
    rows = await db.execute(
        select(AuditLog).where(*filters).order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page).limit(per_page)
    )
    return AuditLogListResponse(
        data=[AuditLogResponse.model_validate(r) for r in rows.scalars().all()],
        pagination=paginate_meta(page, per_page, total or 0),
    )
