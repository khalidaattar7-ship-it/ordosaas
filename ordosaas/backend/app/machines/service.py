"""Machines business logic."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import conflict, not_found
from app.machines.schemas import (
    CreateMachineRequest,
    MachineListResponse,
    MachineResponse,
    PatchMachineRequest,
)
from app.models.machine import Machine
from app.models.operation import Operation


async def list_machines(tenant_id, db: AsyncSession) -> MachineListResponse:
    rows = await db.execute(
        select(Machine).where(Machine.tenant_id == tenant_id).order_by(Machine.external_id)
    )
    return MachineListResponse(
        data=[MachineResponse.model_validate(m) for m in rows.scalars().all()]
    )


async def create_machine(tenant_id, data: CreateMachineRequest, db) -> MachineResponse:
    existing = await db.execute(
        select(Machine).where(
            Machine.tenant_id == tenant_id, Machine.external_id == data.external_id
        )
    )
    if existing.scalar_one_or_none():
        raise conflict("Une machine avec cet external_id existe déjà")
    machine = Machine(
        tenant_id=tenant_id,
        external_id=data.external_id,
        name=data.name,
        description=data.description,
    )
    db.add(machine)
    await db.commit()
    await db.refresh(machine)
    return MachineResponse.model_validate(machine)


async def _get_machine(tenant_id, machine_id, db) -> Machine:
    machine = await db.get(Machine, machine_id)
    if machine is None or machine.tenant_id != tenant_id:
        raise not_found("Machine introuvable")
    return machine


async def patch_machine(tenant_id, machine_id, data: PatchMachineRequest, db) -> MachineResponse:
    machine = await _get_machine(tenant_id, machine_id, db)
    if data.name is not None:
        machine.name = data.name
    if data.status is not None:
        machine.status = data.status
    await db.commit()
    await db.refresh(machine)
    return MachineResponse.model_validate(machine)


async def delete_machine(tenant_id, machine_id, db) -> None:
    machine = await _get_machine(tenant_id, machine_id, db)
    ref_count = await db.scalar(
        select(func.count()).select_from(Operation).where(Operation.machine_id == machine_id)
    )
    if ref_count:
        raise conflict(
            "Machine référencée par des opérations existantes",
            detail={"operations": ref_count},
        )
    await db.delete(machine)
    await db.commit()
    return None
