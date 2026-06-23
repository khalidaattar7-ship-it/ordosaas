"""Tenant business logic."""
from app.errors import not_found
from app.models.tenant import Tenant
from app.tenant.schemas import PatchTenantRequest, TenantLimits, TenantResponse


def _response(t: Tenant) -> TenantResponse:
    return TenantResponse(
        id=t.id, name=t.name, slug=t.slug, default_wr=t.default_wr,
        default_timeout=t.default_timeout, default_strategy=t.default_strategy,
        timezone=t.timezone,
        limits=TenantLimits(
            max_jobs_per_instance=t.max_jobs_per_instance,
            max_machines_per_instance=t.max_machines_per_instance,
            max_instances_stored=t.max_instances_stored,
        ),
    )


async def get_tenant(tenant_id, db) -> TenantResponse:
    t = await db.get(Tenant, tenant_id)
    if t is None:
        raise not_found("Tenant introuvable")
    return _response(t)


async def patch_tenant(tenant_id, data: PatchTenantRequest, db) -> TenantResponse:
    t = await db.get(Tenant, tenant_id)
    if t is None:
        raise not_found("Tenant introuvable")
    if data.name is not None:
        t.name = data.name
    if data.default_wr is not None:
        t.default_wr = data.default_wr
    if data.default_timeout is not None:
        t.default_timeout = data.default_timeout
    if data.default_strategy is not None:
        t.default_strategy = data.default_strategy
    if data.timezone is not None:
        t.timezone = data.timezone
    await db.commit()
    await db.refresh(t)
    return _response(t)
