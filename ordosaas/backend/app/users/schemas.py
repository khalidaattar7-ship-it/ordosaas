"""Pydantic schemas for the users module."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr

from app.common import PaginationMeta


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    role: str
    status: str
    last_login_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    data: list[UserResponse]
    pagination: PaginationMeta


class InviteRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "planificateur", "lecteur"]


class InviteResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    invitation_expires: datetime | None = None


class PatchUserRequest(BaseModel):
    role: Literal["admin", "planificateur", "lecteur"] | None = None
    status: Literal["active", "inactive", "pending"] | None = None


class PatchMeRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    current_password: str | None = None
    new_password: str | None = None
