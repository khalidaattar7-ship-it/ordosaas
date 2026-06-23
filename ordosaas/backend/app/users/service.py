"""Users business logic."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import hash_password, verify_password
from app.common import paginate_meta
from app.errors import bad_request, conflict, forbidden, not_found
from app.models.user import User
from app.users.schemas import (
    InviteResponse,
    PatchMeRequest,
    PatchUserRequest,
    UserListResponse,
    UserResponse,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def list_users(
    tenant_id, page, per_page, role, status, search, db: AsyncSession
) -> UserListResponse:
    filters = [User.tenant_id == tenant_id]
    if role:
        filters.append(User.role == role)
    if status:
        filters.append(User.status == status)
    if search:
        like = f"%{search}%"
        filters.append(
            or_(User.email.ilike(like), User.first_name.ilike(like), User.last_name.ilike(like))
        )

    total = await db.scalar(select(func.count()).select_from(User).where(*filters))
    rows = await db.execute(
        select(User).where(*filters).order_by(User.created_at.desc())
        .offset((page - 1) * per_page).limit(per_page)
    )
    users = rows.scalars().all()
    return UserListResponse(
        data=[UserResponse.model_validate(u) for u in users],
        pagination=paginate_meta(page, per_page, total or 0),
    )


async def invite_user(tenant_id, email, role, db: AsyncSession) -> InviteResponse:
    existing = await db.execute(
        select(User).where(User.tenant_id == tenant_id, User.email == email)
    )
    if existing.scalar_one_or_none():
        raise conflict("Un utilisateur avec cet email existe déjà")
    user = User(
        tenant_id=tenant_id,
        email=email,
        role=role,
        status="pending",
        invitation_token=str(uuid.uuid4()),
        invitation_expires=_now() + timedelta(days=7),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return InviteResponse(
        id=user.id, email=user.email, role=user.role,
        status=user.status, invitation_expires=user.invitation_expires,
    )


async def _get_user(tenant_id, user_id, db) -> User:
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise not_found("Utilisateur introuvable")
    return user


async def patch_user(tenant_id, user_id, data: PatchUserRequest, current_user, db) -> UserResponse:
    user = await _get_user(tenant_id, user_id, db)
    if data.role is not None:
        if user.id == current_user.id:
            raise forbidden("Vous ne pouvez pas modifier votre propre rôle")
        user.role = data.role
    if data.status is not None:
        if user.id == current_user.id and data.status != "active":
            raise forbidden("Vous ne pouvez pas désactiver votre propre compte")
        user.status = data.status
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


async def delete_user(tenant_id, user_id, db) -> None:
    user = await _get_user(tenant_id, user_id, db)
    await db.delete(user)
    await db.commit()
    return None


async def get_me(user_id, db) -> UserResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise not_found("Utilisateur introuvable")
    return UserResponse.model_validate(user)


async def patch_me(user_id, data: PatchMeRequest, db) -> UserResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise not_found("Utilisateur introuvable")
    if data.first_name is not None:
        user.first_name = data.first_name
    if data.last_name is not None:
        user.last_name = data.last_name
    if data.new_password:
        if not data.current_password or not user.password_hash or not verify_password(
            data.current_password, user.password_hash
        ):
            raise bad_request("Mot de passe actuel incorrect")
        user.password_hash = hash_password(data.new_password)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)
