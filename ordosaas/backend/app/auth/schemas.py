"""Pydantic schemas for the auth module."""
import uuid

from pydantic import BaseModel, EmailStr


class UserInToken(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    role: str
    tenant_id: uuid.UUID
    tenant_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
    user: UserInToken


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str
    first_name: str
    last_name: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str
