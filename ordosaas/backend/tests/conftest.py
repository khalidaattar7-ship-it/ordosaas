"""Shared pytest fixtures: scheduling helpers + API integration harness."""
import os
from collections import defaultdict

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.auth.utils import hash_password
from app.database import Base
from app.dependencies import get_db
from app.main import app
from app.models.tenant import Tenant
from app.models.user import User
from scheduling.models.job import Job, Operation, ProblemInstance

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://ordosaas_app:dev_password_change_me@localhost:5432/ordosaas_test",
)

ADMIN_EMAIL = "admin@ensias-demo.ma"
ADMIN_PASSWORD = "demo_password"


# --------------------------------------------------------------------------
# Scheduling fixtures (no DB required)
# --------------------------------------------------------------------------
@pytest.fixture
def small_instance() -> ProblemInstance:
    """3 jobs x 2 machines reference instance."""
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 30, 1), Operation("J1", "M2", 20, 2)],
            deadline=120, weight=8.5),
        Job(id="J2", operations=[Operation("J2", "M2", 25, 1), Operation("J2", "M1", 18, 2)],
            deadline=95, weight=3.0),
        Job(id="J3", operations=[Operation("J3", "M1", 22, 1), Operation("J3", "M2", 12, 2)],
            deadline=150, weight=5.0),
    ]
    setup_times = {
        ("J1", "J2", "M1"): 8, ("J2", "J1", "M1"): 6, ("J1", "J3", "M1"): 5,
        ("J3", "J1", "M1"): 7, ("J2", "J3", "M1"): 4, ("J3", "J2", "M1"): 9,
        ("J1", "J2", "M2"): 5, ("J2", "J1", "M2"): 3, ("J1", "J3", "M2"): 6,
        ("J3", "J1", "M2"): 4, ("J2", "J3", "M2"): 7, ("J3", "J2", "M2"): 5,
    }
    return ProblemInstance(jobs=jobs, machines=["M1", "M2"], setup_times=setup_times, wr=1)


def assert_no_machine_overlap(schedule):
    """Helper: assert no two intervals overlap on any machine (ops + setups)."""
    slots = defaultdict(list)
    for entry in schedule.entries:
        slots[entry.machine_id].append((entry.start_time, entry.end_time))
        if entry.setup and entry.setup.duration > 0:
            slots[entry.machine_id].append((entry.setup.start_time, entry.setup.end_time))
    for machine, intervals in slots.items():
        intervals.sort()
        for i in range(len(intervals) - 1):
            assert intervals[i][1] <= intervals[i + 1][0], (
                f"Overlap on {machine}: {intervals[i]} and {intervals[i + 1]}"
            )


# --------------------------------------------------------------------------
# API integration fixtures (require Postgres — used in CI)
# --------------------------------------------------------------------------
@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seeded_admin(db_session):
    """Ensure a known admin user exists for authentication tests."""
    from sqlalchemy import select

    res = await db_session.execute(select(User).where(User.email == ADMIN_EMAIL))
    user = res.scalar_one_or_none()
    if user is None:
        tenant = Tenant(name="ENSIAS Demo", slug="ensias-demo")
        db_session.add(tenant)
        await db_session.flush()
        user = User(
            tenant_id=tenant.id, email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            first_name="Admin", last_name="Demo", role="admin", status="active",
        )
        db_session.add(user)
        await db_session.commit()
    return user


@pytest_asyncio.fixture
async def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_token(client, seeded_admin):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
