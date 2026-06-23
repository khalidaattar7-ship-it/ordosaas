"""Auth business logic: login, refresh, invitation and password reset."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import TokenResponse, UserInToken
from app.auth.utils import (
    JWTError,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.config import settings
from app.errors import bad_request, forbidden, unauthorized
from app.models.tenant import Tenant
from app.models.user import User

# Simple in-memory token blacklist (replace with Redis in production).
_BLACKLIST: set[str] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _build_token_response(user: User, tenant: Tenant) -> TokenResponse:
    claims = {"sub": str(user.id), "tenant_id": str(user.tenant_id), "role": user.role}
    access = create_access_token(claims)
    refresh = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=access,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=refresh,
        user=UserInToken(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role,
            tenant_id=user.tenant_id,
            tenant_name=tenant.name if tenant else "",
        ),
    )


async def _load_user_by_email(db: AsyncSession, email: str) -> User | None:
    res = await db.execute(select(User).where(User.email == email))
    return res.scalar_one_or_none()


async def login(email: str, password: str, db: AsyncSession) -> TokenResponse:
    user = await _load_user_by_email(db, email)
    if user is None or not user.password_hash:
        raise unauthorized("Email ou mot de passe incorrect")
    if not verify_password(password, user.password_hash):
        raise unauthorized("Email ou mot de passe incorrect")
    if user.status != "active":
        raise forbidden("Compte inactif ou en attente d'activation")

    user.last_login_at = _now()
    tenant = await db.get(Tenant, user.tenant_id)
    await db.commit()
    await db.refresh(user)
    return await _build_token_response(user, tenant)


async def refresh(refresh_token: str, db: AsyncSession) -> TokenResponse:
    try:
        payload = verify_token(refresh_token)
    except JWTError:
        raise unauthorized("Refresh token invalide")
    if payload.get("type") != "refresh":
        raise unauthorized("Type de token invalide")
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise unauthorized("Utilisateur introuvable")
    tenant = await db.get(Tenant, user.tenant_id)
    return await _build_token_response(user, tenant)


async def logout(token: str, db: AsyncSession) -> None:
    if token:
        _BLACKLIST.add(token)
    return None


async def accept_invitation(
    token: str, password: str, first_name: str, last_name: str, db: AsyncSession
) -> TokenResponse:
    res = await db.execute(select(User).where(User.invitation_token == token))
    user = res.scalar_one_or_none()
    if user is None:
        raise bad_request("Invitation invalide")
    if user.invitation_expires and user.invitation_expires < _now():
        raise bad_request("Invitation expirée")

    user.password_hash = hash_password(password)
    user.first_name = first_name
    user.last_name = last_name
    user.status = "active"
    user.invitation_token = None
    user.invitation_expires = None
    user.last_login_at = _now()
    tenant = await db.get(Tenant, user.tenant_id)
    await db.commit()
    await db.refresh(user)
    return await _build_token_response(user, tenant)


async def forgot_password(email: str, db: AsyncSession) -> None:
    user = await _load_user_by_email(db, email)
    if user is None:
        # Do not leak existence of accounts.
        return None
    user.reset_token = str(uuid.uuid4())
    user.reset_expires = _now() + timedelta(hours=1)
    await db.commit()
    if settings.ENVIRONMENT != "production":
        print(f"[DEV] reset token for {email}: {user.reset_token}")
    return None


async def reset_password(token: str, password: str, db: AsyncSession) -> None:
    res = await db.execute(select(User).where(User.reset_token == token))
    user = res.scalar_one_or_none()
    if user is None:
        raise bad_request("Token de réinitialisation invalide")
    if user.reset_expires and user.reset_expires < _now():
        raise bad_request("Token de réinitialisation expiré")
    user.password_hash = hash_password(password)
    user.reset_token = None
    user.reset_expires = None
    await db.commit()
    return None
