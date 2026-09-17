"""`time_windows.method_used` n'accepte que les methodes reelles (audit du 2026-09-17).

OCCURRENCE DU MOTIF RECURRENT nomme dans "Approche & patterns" : une contrainte prevue
sur le papier que la base n'applique pas. Meme famille que H8/H9, D16/D17 et H10a/b/c —
et c'est pour cela qu'elle est verrouillee par un test, sur le modele exact des cinq
valeurs de `PerturbationType` en D15.

Ce que la contrainte valait AVANT :

  - `schema_bdd.sql` declarait CHECK (method_used IN ('cpsat','atcs', NULL)). En SQL,
    `'zzz' IN ('cpsat','atcs',NULL)` vaut NULL, jamais FALSE, et un CHECK qui vaut NULL
    PASSE : la contrainte du document acceptait n'importe quelle valeur.
  - La migration 0001 et le modele n'en portaient AUCUNE. La colonne etait libre.

La liste du schema etait par ailleurs perimee : `lns` et `incremental` sont nes apres
lui, et `app/resolutions/service.py:191` les ecrit reellement.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import TimeWindow  # noqa: F401
from app.models import (  # noqa: F401 — enregistre toutes les tables
    ProblemInstance,
    Resolution,
    SolverConfig,
    Tenant,
    User,
)
from tests.bdd_fixtures import cree_graphe_minimal

METHODES_REELLES = ["cpsat", "lns", "atcs", "incremental"]
METHODES_REFUSEES = ["optimal", "feasible", "atcs_fallback", "frozen", "zzz", ""]


@pytest_asyncio.fixture
async def session_fk() -> AsyncSession:
    """SQLite avec les CHECK actifs, schema cree depuis les modeles."""
    moteur = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with moteur.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fabrique = sessionmaker(moteur, class_=AsyncSession, expire_on_commit=False)
    async with fabrique() as s:
        yield s
    await moteur.dispose()


async def _fenetre(session, methode):
    graphe = await cree_graphe_minimal(session)
    fenetre = TimeWindow(
        tenant_id=graphe["tenant"].id,
        resolution_id=graphe["resolution"].id,
        window_index=1, t_start=0, t_end=100, nb_jobs=3,
        status="feasible", method_used=methode,
    )
    session.add(fenetre)
    await session.commit()
    return fenetre


@pytest.mark.asyncio
@pytest.mark.parametrize("methode", METHODES_REELLES)
async def test_les_methodes_reellement_produites_sont_acceptees(session_fk, methode):
    """Les quatre valeurs que le code ecrit doivent passer.

    C'est l'assertion qui aurait rejete la liste litterale du schema
    (`IN ('cpsat','atcs')`) : elle aurait casse `lns` et `incremental`.
    """
    fenetre = await _fenetre(session_fk, methode)
    assert fenetre.method_used == methode


@pytest.mark.asyncio
async def test_labsence_de_methode_reste_permise(session_fk):
    """`method_used` est nullable : une fenetre en cours n'en a pas encore."""
    fenetre = await _fenetre(session_fk, None)
    assert fenetre.method_used is None


@pytest.mark.asyncio
@pytest.mark.parametrize("methode", METHODES_REFUSEES)
async def test_une_methode_hors_liste_est_refusee_par_la_base(session_fk, methode):
    """C'est le test qui echoue sans la contrainte : la colonne acceptait tout.

    `optimal` et `feasible` ne sont pas choisis au hasard : ce sont exactement les
    valeurs que le solveur stockait a tort dans `resolutions.method_used`, ce qu'a
    du corriger la migration 0003.
    """
    with pytest.raises(IntegrityError):
        await _fenetre(session_fk, methode)


@pytest.mark.asyncio
async def test_la_contrainte_rejette_vraiment_et_ne_vaut_pas_null(session_fk):
    """Le piege `IN (..., NULL)` : un CHECK qui vaut NULL passe au lieu de rejeter.

    Ce test distingue une contrainte qui REJETTE d'une contrainte qui existe. Ecrite
    sous la forme du schema, elle aurait laisse passer `zzz` sans broncher.
    """
    async with session_fk.bind.begin() as conn:
        sql = (await conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='time_windows'"
        ))).scalar_one()
    assert "ck_window_method" in sql, "la contrainte n'est pas dans le DDL de la table"
    assert "IS NULL" in sql, (
        "la contrainte doit utiliser `OR method_used IS NULL`, jamais `IN (..., NULL)` "
        "qui ne rejette rien"
    )
