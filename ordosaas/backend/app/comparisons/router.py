"""Comparisons API router."""
from fastapi import APIRouter, Depends, status

from app.comparisons import service
from app.comparisons.schemas import CompareRequest, ComparisonResponse
from app.dependencies import CurrentUser, DbSession, require_planificateur

router = APIRouter()


@router.post(
    "", response_model=ComparisonResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_planificateur)],
)
async def create_comparison(payload: CompareRequest, current_user: CurrentUser, db: DbSession):
    return await service.compare(
        current_user.tenant_id, current_user.id,
        payload.resolution_a_id, payload.resolution_b_id, db,
    )
