"""
Graphe de donnees minimal pour les tests de persistance.

Factorise ici plutot que duplique dans chaque test : ce graphe
(tenant → user → instance → config → resolution) sera directement reutile quand la
Discussion 4 branchera l'authentification reelle et les endpoints.

## Pourquoi SQLite

`app/models/_types.py` fournit des types portables (`UUID`, `JSONB`) qui compilent sur
PostgreSQL comme sur SQLite, ce dernier etant documente comme repli local. Les tests
creent donc le schema depuis les MODELES (`Base.metadata.create_all`) et non depuis les
migrations Alembic, qui sont du SQL PostgreSQL. Les deux doivent rester coherents : la
migration 0004 reproduit ce que declarent les modeles.

Consequence pratique : ces tests relisent une VRAIE base et n'ont besoin d'aucun
PostgreSQL local — dont l'absence explique les echecs preexistants de `test_instances`,
`test_auth` et `test_resolutions`.
"""
import uuid
from datetime import datetime, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (  # noqa: F401 — enregistre toutes les tables dans la metadata
    Machine,
    ProblemInstance,
    Resolution,
    SectorDefault,
    SolverConfig,
    Tenant,
    User,
)
from app.sectors import seme_le_socle


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Une base SQLite en memoire, schema cree depuis les modeles, isolee par test."""
    moteur = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with moteur.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    fabrique = sessionmaker(moteur, class_=AsyncSession, expire_on_commit=False)
    async with fabrique() as s:
        yield s
    await moteur.dispose()


@pytest_asyncio.fixture
async def socle(session) -> AsyncSession:
    """Session dont la table `sector_defaults` est semee du socle initial."""
    await seme_le_socle(session)
    await session.commit()
    return session


async def cree_graphe_minimal(
    session: AsyncSession,
    secteur: str = "autre",
    slug: str | None = None,
) -> dict:
    """Cree tenant → user → instance → config → resolution, et renvoie les objets.

    C'est le graphe minimal qu'exigent les cles etrangeres de `perturbation_events` :
    `tenant_id`, `base_resolution_id` et `reported_by` y sont tous NOT NULL, comme le
    prevoit le schema de conception.

    Returns:
        {"tenant", "user", "instance", "config", "resolution"}
    """
    suffixe = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Atelier {suffixe}",
        slug=slug or f"atelier-{suffixe}",
        sector=secteur,
    )
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        email=f"chef-{suffixe}@exemple.ma",
        password_hash="x" * 60,
        first_name="Chef",
        last_name="Atelier",
        role="admin",
        status="active",
    )
    session.add(user)
    await session.flush()

    instance = ProblemInstance(
        tenant_id=tenant.id,
        name=f"Instance {suffixe}",
        nb_jobs=10,
        nb_machines=3,
        created_by=user.id,
    )
    session.add(instance)
    await session.flush()

    config = SolverConfig(
        tenant_id=tenant.id,
        instance_id=instance.id,
        created_by=user.id,
    )
    session.add(config)
    await session.flush()

    resolution = Resolution(
        tenant_id=tenant.id,
        instance_id=instance.id,
        config_id=config.id,
        triggered_by=user.id,
        status="completed",
        completed_at=datetime.now(timezone.utc),
    )
    session.add(resolution)
    await session.flush()

    return {
        "tenant": tenant,
        "user": user,
        "instance": instance,
        "config": config,
        "resolution": resolution,
    }
