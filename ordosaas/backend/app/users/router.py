"""Users API router."""
from fastapi import APIRouter, Depends, Query, status

from app.dependencies import CurrentUser, DbSession, require_admin
from app.users import service
from app.users.schemas import (
    InviteRequest,
    InviteResponse,
    PatchMeRequest,
    PatchUserRequest,
    UserListResponse,
    UserResponse,
)

router = APIRouter()


@router.get("", response_model=UserListResponse, dependencies=[Depends(require_admin)])
async def list_users(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    role: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = None,
):
    return await service.list_users(
        current_user.tenant_id, page, per_page, role, status_filter, search, db
    )


@router.post(
    "/invite", response_model=InviteResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def invite_user(payload: InviteRequest, current_user: CurrentUser, db: DbSession):
    return await service.invite_user(current_user.tenant_id, payload.email, payload.role, db)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser, db: DbSession):
    return await service.get_me(current_user.id, db)


@router.patch("/me", response_model=UserResponse)
async def patch_me(payload: PatchMeRequest, current_user: CurrentUser, db: DbSession):
    return await service.patch_me(current_user.id, payload, db)


@router.patch("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
async def patch_user(user_id, payload: PatchUserRequest, current_user: CurrentUser, db: DbSession):
    return await service.patch_user(current_user.tenant_id, user_id, payload, current_user, db)


@router.delete(
    "/{user_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_user(user_id, current_user: CurrentUser, db: DbSession):
    await service.delete_user(current_user.tenant_id, user_id, db)
