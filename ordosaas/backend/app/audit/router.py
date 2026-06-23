"""audit API router (scaffold)."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/ping", tags=["audit"])
async def ping_audit():
    return {"module": "audit", "status": "ok"}
