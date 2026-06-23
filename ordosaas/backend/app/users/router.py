"""users API router (scaffold)."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/ping", tags=["users"])
async def ping_users():
    return {"module": "users", "status": "ok"}
