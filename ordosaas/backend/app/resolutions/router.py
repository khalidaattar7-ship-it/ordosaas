"""resolutions API router (scaffold)."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/ping", tags=["resolutions"])
async def ping_resolutions():
    return {"module": "resolutions", "status": "ok"}
