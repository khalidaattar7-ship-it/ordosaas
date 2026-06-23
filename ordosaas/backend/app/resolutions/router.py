"""Resolutions API router."""
from fastapi import APIRouter, Depends, Query, status

from app.dependencies import CurrentUser, DbSession, require_planificateur
from app.resolutions import service
from app.resolutions.schemas import (
    GanttResponse,
    JobDetailInResolution,
    ResolutionStatus,
)

router = APIRouter()


@router.get("/{resolution_id}", response_model=ResolutionStatus)
async def get_resolution(resolution_id, current_user: CurrentUser, db: DbSession):
    return await service.get_resolution(current_user.tenant_id, resolution_id, db)


@router.get("/{resolution_id}/gantt", response_model=GanttResponse)
async def get_gantt(
    resolution_id,
    current_user: CurrentUser,
    db: DbSession,
    machine_ids: list[str] | None = Query(None),
    t_start: int | None = None,
    t_end: int | None = None,
    include_setups: bool = True,
    include_windows: bool = True,
):
    return await service.get_gantt(
        current_user.tenant_id, resolution_id, machine_ids, t_start, t_end,
        include_setups, include_windows, db,
    )


@router.get("/{resolution_id}/jobs/{job_id}", response_model=JobDetailInResolution)
async def get_job_in_resolution(resolution_id, job_id, current_user: CurrentUser, db: DbSession):
    return await service.get_job_in_resolution(current_user.tenant_id, resolution_id, job_id, db)


@router.delete(
    "/{resolution_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_planificateur)],
)
async def delete_resolution(resolution_id, current_user: CurrentUser, db: DbSession):
    await service.delete_resolution(current_user.tenant_id, resolution_id, db)


@router.post(
    "/{resolution_id}/cancel", response_model=ResolutionStatus,
    dependencies=[Depends(require_planificateur)],
)
async def cancel_resolution(resolution_id, current_user: CurrentUser, db: DbSession):
    return await service.cancel_resolution(current_user.tenant_id, resolution_id, db)
