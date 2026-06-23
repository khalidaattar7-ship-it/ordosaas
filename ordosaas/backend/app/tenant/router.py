"""tenant API router (scaffold)."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/ping", tags=["tenant"])
async def ping_tenant():
    return {"module": "tenant", "status": "ok"}
