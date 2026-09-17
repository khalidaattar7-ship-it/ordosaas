"""Les index specifies par `schema_bdd.sql` existent reellement (audit du 2026-09-17).

La migration 0001 creait 13 index la ou le schema de conception en specifie 29. Pour les
7 tables auditees, 9 manquaient — tous sur une cle etrangere ou sur `tenant_id`, plus le
composite explicitement justifie dans le schema pour la requete Gantt.

Ce module verrouille la propriete OBSERVABLE : l'index existe dans la base reellement
creee depuis les modeles. Il ne teste pas la migration Alembic, qui est du SQL
PostgreSQL non executable ici — c'est la limite deja documentee dans `bdd_fixtures` :
modeles et migrations doivent rester coherents, et c'est une discipline, pas une
verification automatique.

Les index des 7 tables sont declares dans les modeles, y compris ceux que 0001 creait
deja, pour que ces tables soient entierement auto-descriptives. La convention de nommage
suivie est celle de la MIGRATION (`idx_jobs_tenant`) et non celle du schema
(`idx_jobs_tenant_id`), pour rester coherente avec les 13 index existants.
"""
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import Base
from app.models import (  # noqa: F401 — enregistre toutes les tables dans la metadata
    Job,
    Machine,
    Operation,
    ScheduleEntry,
    SetupTime,
    SolutionComparison,
    TimeWindow,
)

# (table, nom de l'index, colonnes attendues dans l'ordre)
INDEX_ATTENDUS = [
    ("machines", "idx_machines_tenant", ["tenant_id"]),
    ("jobs", "idx_jobs_instance", ["instance_id"]),
    ("jobs", "idx_jobs_tenant", ["tenant_id"]),
    ("operations", "idx_operations_job", ["job_id"]),
    ("operations", "idx_operations_machine", ["machine_id"]),
    ("operations", "idx_operations_tenant", ["tenant_id"]),
    ("setup_times", "idx_setups_instance", ["instance_id"]),
    ("setup_times", "idx_setups_from_job", ["from_job_id"]),
    ("setup_times", "idx_setups_to_job", ["to_job_id"]),
    ("setup_times", "idx_setups_machine", ["machine_id"]),
    ("time_windows", "idx_windows_resolution", ["resolution_id"]),
    ("schedule_entries", "idx_entries_resolution", ["resolution_id"]),
    ("schedule_entries", "idx_entries_machine", ["machine_id"]),
    ("schedule_entries", "idx_entries_job", ["job_id"]),
    ("schedule_entries", "idx_entries_tenant", ["tenant_id"]),
    ("schedule_entries", "idx_entries_gantt",
     ["resolution_id", "machine_id", "start_time"]),
    ("solution_comparisons", "idx_comparisons_tenant", ["tenant_id"]),
]


@pytest_asyncio.fixture
async def moteur():
    """Base SQLite en memoire, schema cree depuis les MODELES."""
    m = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with m.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield m
    await m.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("table,nom,colonnes", INDEX_ATTENDUS)
async def test_lindex_existe_dans_la_base_reelle(moteur, table, nom, colonnes):
    async with moteur.begin() as conn:
        lignes = (await conn.execute(text(f"PRAGMA index_list('{table}')"))).fetchall()
        noms = {ligne[1] for ligne in lignes}
        assert nom in noms, (
            f"index {nom} absent de {table} ; presents : {sorted(noms)}"
        )
        infos = (await conn.execute(text(f"PRAGMA index_info('{nom}')"))).fetchall()
    obtenues = [ligne[2] for ligne in infos]
    assert obtenues == colonnes, (
        f"{nom} porte sur {obtenues}, attendu {colonnes}"
    )


@pytest.mark.asyncio
async def test_lindex_gantt_est_bien_un_composite_ordonne(moteur):
    """L'ordre des colonnes fait la valeur de cet index : il sert un tri par date.

    Un index sur les memes colonnes dans un autre ordre ne rendrait pas le meme
    service a la requete Gantt.
    """
    async with moteur.begin() as conn:
        infos = (
            await conn.execute(text("PRAGMA index_info('idx_entries_gantt')"))
        ).fetchall()
    assert [ligne[2] for ligne in infos] == [
        "resolution_id", "machine_id", "start_time",
    ]
