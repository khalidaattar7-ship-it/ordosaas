"""auth API router (scaffold)."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/ping", tags=["auth"])
async def ping_auth():
    return {"module": "auth", "status": "ok"}
