"""Machines API router."""
from fastapi import APIRouter, Depends, status

from app.dependencies import CurrentUser, DbSession, require_admin
from app.machines import service
from app.machines.schemas import (
    CreateMachineRequest,
    MachineListResponse,
    MachineResponse,
    PatchMachineRequest,
)

router = APIRouter()


@router.get("", response_model=MachineListResponse)
async def list_machines(current_user: CurrentUser, db: DbSession):
    return await service.list_machines(current_user.tenant_id, db)


@router.post(
    "", response_model=MachineResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_machine(payload: CreateMachineRequest, current_user: CurrentUser, db: DbSession):
    return await service.create_machine(current_user.tenant_id, payload, db)


@router.patch("/{machine_id}", response_model=MachineResponse, dependencies=[Depends(require_admin)])
async def patch_machine(machine_id, payload: PatchMachineRequest, current_user: CurrentUser, db: DbSession):
    return await service.patch_machine(current_user.tenant_id, machine_id, payload, db)


@router.delete(
    "/{machine_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_machine(machine_id, current_user: CurrentUser, db: DbSession):
    await service.delete_machine(current_user.tenant_id, machine_id, db)
