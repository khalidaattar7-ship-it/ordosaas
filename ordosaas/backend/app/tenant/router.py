"""Tenant API router."""
from fastapi import APIRouter, Depends

from app.dependencies import CurrentUser, DbSession, require_admin
from app.tenant import service
from app.tenant.schemas import PatchTenantRequest, TenantResponse

router = APIRouter()


@router.get("", response_model=TenantResponse)
async def get_tenant(current_user: CurrentUser, db: DbSession):
    return await service.get_tenant(current_user.tenant_id, db)


@router.patch("", response_model=TenantResponse, dependencies=[Depends(require_admin)])
async def patch_tenant(payload: PatchTenantRequest, current_user: CurrentUser, db: DbSession):
    return await service.patch_tenant(current_user.tenant_id, payload, db)
