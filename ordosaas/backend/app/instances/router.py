"""instances API router (scaffold)."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/ping", tags=["instances"])
async def ping_instances():
    return {"module": "instances", "status": "ok"}
