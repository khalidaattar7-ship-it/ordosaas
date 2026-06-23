"""comparisons API router (scaffold)."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/ping", tags=["comparisons"])
async def ping_comparisons():
    return {"module": "comparisons", "status": "ok"}
