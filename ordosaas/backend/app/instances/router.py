"""Instances API router."""
from fastapi import APIRouter, Depends, Form, Query, UploadFile, status

from app.dependencies import CurrentUser, DbSession, require_admin, require_planificateur
from app.instances import service
from app.instances.schemas import (
    AddJobRequest,
    ImportResponse,
    InstanceListResponse,
    InstanceResponse,
    JobListResponse,
    JobResponse,
    PatchJobRequest,
)
from app.resolutions import service as resolution_service
from app.resolutions.schemas import ResolveRequest, ResolveResponse

router = APIRouter()


@router.post(
    "/{instance_id}/resolve", response_model=ResolveResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_planificateur)],
)
async def resolve_instance(
    instance_id, payload: ResolveRequest, current_user: CurrentUser, db: DbSession
):
    return await resolution_service.resolve(
        instance_id, payload, current_user.tenant_id, current_user.id, db
    )


async def _read(file: UploadFile | None) -> str | None:
    if file is None:
        return None
    return (await file.read()).decode("utf-8-sig")


@router.get("", response_model=InstanceListResponse)
async def list_instances(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    return await service.list_instances(current_user.tenant_id, page, per_page, db)


@router.post(
    "/import", response_model=ImportResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_planificateur)],
)
async def import_instance(
    current_user: CurrentUser,
    db: DbSession,
    name: str = Form(...),
    description: str | None = Form(None),
    jobs_file: UploadFile = ...,
    operations_file: UploadFile = ...,
    setups_file: UploadFile | None = None,
):
    return await service.import_instance(
        name, description,
        await _read(jobs_file), await _read(operations_file), await _read(setups_file),
        current_user.tenant_id, current_user.id, db,
    )


@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(instance_id, current_user: CurrentUser, db: DbSession):
    return await service.get_instance(current_user.tenant_id, instance_id, db)


@router.get("/{instance_id}/jobs", response_model=JobListResponse)
async def list_jobs(
    instance_id,
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    return await service.list_jobs(current_user.tenant_id, instance_id, page, per_page, db)


@router.post(
    "/{instance_id}/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_planificateur)],
)
async def add_job(instance_id, payload: AddJobRequest, current_user: CurrentUser, db: DbSession):
    return await service.add_job(current_user.tenant_id, instance_id, payload, db)


@router.patch(
    "/{instance_id}/jobs/{job_id}", response_model=JobResponse,
    dependencies=[Depends(require_planificateur)],
)
async def patch_job(
    instance_id, job_id, payload: PatchJobRequest, current_user: CurrentUser, db: DbSession
):
    return await service.patch_job(current_user.tenant_id, instance_id, job_id, payload, db)


@router.delete(
    "/{instance_id}/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_planificateur)],
)
async def delete_job(instance_id, job_id, current_user: CurrentUser, db: DbSession):
    await service.delete_job(current_user.tenant_id, instance_id, job_id, db)


@router.delete(
    "/{instance_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_instance(instance_id, current_user: CurrentUser, db: DbSession):
    await service.delete_instance(current_user.tenant_id, instance_id, db)
