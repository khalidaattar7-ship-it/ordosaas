"""machines API router (scaffold)."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/ping", tags=["machines"])
async def ping_machines():
    return {"module": "machines", "status": "ok"}
