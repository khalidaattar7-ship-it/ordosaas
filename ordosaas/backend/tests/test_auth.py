"""Integration tests for the auth + users/me endpoints."""
import pytest

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

pytestmark = pytest.mark.asyncio


async def test_login_success(client, seeded_admin):
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == ADMIN_EMAIL


async def test_login_bad_credentials(client, seeded_admin):
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": "wrong_password"},
    )
    assert res.status_code == 401


async def test_login_inactive_account(client, db_session):
    from app.auth.utils import hash_password
    from app.models.tenant import Tenant
    from app.models.user import User

    tenant = Tenant(name="Inactive Co", slug="inactive-co")
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(User(
        tenant_id=tenant.id, email="inactive@demo.ma",
        password_hash=hash_password("secret123"), role="lecteur", status="inactive",
    ))
    await db_session.commit()

    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@demo.ma", "password": "secret123"},
    )
    assert res.status_code == 403


async def test_refresh_token(client, seeded_admin):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    refresh_token = login.json()["refresh_token"]
    res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    assert res.json()["access_token"]


async def test_refresh_invalid_token(client):
    res = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert res.status_code == 401


async def test_logout(client, auth_headers):
    res = await client.post("/api/v1/auth/logout", headers=auth_headers)
    assert res.status_code == 204


async def test_get_me_with_token(client, auth_headers):
    res = await client.get("/api/v1/users/me", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["email"] == ADMIN_EMAIL


async def test_get_me_without_token(client):
    res = await client.get("/api/v1/users/me")
    assert res.status_code == 401
