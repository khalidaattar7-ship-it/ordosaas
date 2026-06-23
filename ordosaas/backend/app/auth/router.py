"""Auth API router."""
from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import service
from app.auth.schemas import (
    AcceptInvitationRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.dependencies import DbSession, oauth2_scheme

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession):
    return await service.login(payload.email, payload.password, db)


@router.post("/login/oauth", response_model=TokenResponse, include_in_schema=False)
async def login_oauth(db: DbSession, form: OAuth2PasswordRequestForm = Depends()):
    # Compatibility endpoint for the Swagger "Authorize" button.
    return await service.login(form.username, form.password, db)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DbSession):
    return await service.refresh(payload.refresh_token, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(db: DbSession, token: str = Depends(oauth2_scheme)):
    await service.logout(token, db)


@router.post("/accept-invitation", response_model=TokenResponse)
async def accept_invitation(payload: AcceptInvitationRequest, db: DbSession):
    return await service.accept_invitation(
        payload.token, payload.password, payload.first_name, payload.last_name, db
    )


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(payload: ForgotPasswordRequest, db: DbSession):
    await service.forgot_password(payload.email, db)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(payload: ResetPasswordRequest, db: DbSession):
    await service.reset_password(payload.token, payload.password, db)
