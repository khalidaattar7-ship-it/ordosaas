"""
Secteur du tenant et socle de configuration par secteur (Piste A).

Ces tests verifient que le socle PROPOSE des valeurs, qu'il vit bien en base et non en
constantes applicatives, et qu'il ne s'impose jamais de lui-meme.

Les valeurs testees sont des HYPOTHESES non validees empiriquement. Les assertions
portent donc sur le MECANISME — la table est bien la source, un UPDATE change le
resultat, un secteur inconnu echoue franchement — et sur les deux seuls ecarts
distinctifs du socle initial, pas sur chaque chiffre. Figer tous les chiffres
reviendrait a traiter des hypotheses comme des acquis.
"""
import pytest

from app.models.sector_default import SECTEUR_PAR_DEFAUT, SECTEURS, SectorDefault
from app.sectors import (
    SOCLE_INITIAL,
    SOCLE_NEUTRE,
    SecteurInconnuError,
    defauts_pour_secteur,
    defauts_pour_tenant,
    seme_le_socle,
)
from tests.bdd_fixtures import cree_graphe_minimal, session, socle  # noqa: F401

pytestmark = pytest.mark.asyncio


# -- taxonomie ---------------------------------------------------------------
async def test_le_socle_couvre_toute_la_taxonomie(socle):
    """Aucun secteur ne doit se retrouver sans ligne."""
    lignes = {
        s for (s,) in (await socle.execute(
            SectorDefault.__table__.select().with_only_columns(SectorDefault.sector)
        )).all()
    }
    assert lignes == set(SECTEURS)


async def test_le_secteur_par_defaut_ne_suppose_rien(socle):
    """`autre` reproduit exactement les defauts actuels du projet."""
    defauts = await defauts_pour_secteur(socle, SECTEUR_PAR_DEFAUT)

    for cle, valeur in SOCLE_NEUTRE.items():
        assert defauts[cle] == valeur, f"{cle} devrait valoir le defaut du projet"


async def test_un_secteur_inconnu_echoue_franchement(socle):
    """On ne degrade PAS silencieusement vers `autre`.

    Une valeur hors taxonomie revele un defaut d'appelant ; la masquer la rendrait
    indetectable, exactement le genre de defaut silencieux que ce projet a deja paye
    cher ailleurs.
    """
    with pytest.raises(SecteurInconnuError, match="metallurgie"):
        await defauts_pour_secteur(socle, "metallurgie")


# -- les deux ecarts distinctifs du socle initial -----------------------------
async def test_les_secteurs_a_insertions_relevent_la_stabilite(socle):
    """`cablage_auto` et `textile` : hypothese d'insertions dominantes.

    C'est le seul levier qui les distingue, et la raison pour laquelle
    `stability_weight` a du etre ajoute a `solver_configs` — sans lui, deux secteurs
    sur six n'auraient aucun defaut propre.
    """
    neutre = SOCLE_NEUTRE["stability_weight"]
    for secteur in ("cablage_auto", "textile"):
        defauts = await defauts_pour_secteur(socle, secteur)
        assert defauts["stability_weight"] > neutre, (
            f"{secteur} devrait proposer une stabilite superieure au defaut"
        )
        assert defauts["rationale"], "une hypothese doit porter sa justification"


async def test_les_secteurs_a_aleas_subis_relevent_les_techniciens(socle):
    """`plasturgie` et `sous_traitance_mecanique` : hypothese d'aleas subis.

    La plasturgie doit etre la plus marquee des deux, la sous-traitance mecanique
    etant decrite comme un profil intermediaire.
    """
    neutre = SOCLE_NEUTRE["wr"]
    plasturgie = await defauts_pour_secteur(socle, "plasturgie")
    mecanique = await defauts_pour_secteur(socle, "sous_traitance_mecanique")

    assert plasturgie["wr"] > mecanique["wr"] > neutre


async def test_chaque_hypothese_porte_sa_justification(socle):
    """Aucune valeur sans explication : on doit savoir plus tard ce qu'on reexamine."""
    for secteur in SECTEURS:
        defauts = await defauts_pour_secteur(socle, secteur)
        assert defauts["rationale"], f"{secteur} sans rationale"


# -- la table est bien la source de verite ------------------------------------
async def test_modifier_la_table_change_le_resultat_sans_toucher_au_code(socle):
    """LE critere : les defauts sont adaptables par UPDATE, pas par deploiement."""
    avant = await defauts_pour_secteur(socle, "plasturgie")

    ligne = await socle.get(SectorDefault, "plasturgie")
    ligne.wr = 12
    ligne.stability_weight = 0.42
    await socle.commit()

    apres = await defauts_pour_secteur(socle, "plasturgie")
    assert apres["wr"] == 12 != avant["wr"]
    assert apres["stability_weight"] == pytest.approx(0.42)


async def test_une_table_vide_degrade_vers_le_socle_neutre(session):
    """Sans aucune ligne, on retombe sur les defauts du projet — jamais une erreur."""
    defauts = await defauts_pour_secteur(session, "cablage_auto")

    assert defauts["secteur"] == "cablage_auto"
    assert defauts["rationale"] is None
    for cle, valeur in SOCLE_NEUTRE.items():
        assert defauts[cle] == valeur


async def test_le_semis_est_idempotent(session):
    """Reamorcer ne duplique rien et n'ecrase aucune valeur ajustee."""
    assert await seme_le_socle(session) == len(SECTEURS)
    await session.commit()

    ligne = await session.get(SectorDefault, "autre")
    ligne.wr = 7
    await session.commit()

    assert await seme_le_socle(session) == 0, "rien ne doit etre reinsere"
    await session.commit()

    assert (await session.get(SectorDefault, "autre")).wr == 7, (
        "une valeur ajustee en base ne doit pas etre ecrasee par un reamorcage"
    )


# -- le tenant porte son secteur ----------------------------------------------
async def test_un_tenant_a_toujours_un_secteur(socle):
    """Jamais nul : `autre` par defaut."""
    graphe = await cree_graphe_minimal(socle)
    await socle.commit()

    assert graphe["tenant"].sector == SECTEUR_PAR_DEFAUT


async def test_les_defauts_suivent_le_secteur_du_tenant(socle):
    """Le raccourci par tenant donne bien le socle de SON secteur."""
    graphe = await cree_graphe_minimal(socle, secteur="cablage_auto")
    await socle.commit()

    par_tenant = await defauts_pour_tenant(socle, graphe["tenant"])
    par_secteur = await defauts_pour_secteur(socle, "cablage_auto")
    assert par_tenant == par_secteur


async def test_creer_un_tenant_n_applique_RIEN_automatiquement(socle):
    """Le socle PROPOSE, il n'impose pas — et il ne peut structurellement pas imposer.

    `SolverConfig` exige un `instance_id` : aucune configuration ne peut exister au
    moment ou le tenant est cree. Ce test fige le fait que les defauts du tenant
    restent ceux du modele, intacts, meme pour un secteur qui propose autre chose.
    """
    graphe = await cree_graphe_minimal(socle, secteur="plasturgie")
    await socle.commit()

    propose = await defauts_pour_secteur(socle, "plasturgie")
    assert propose["wr"] != graphe["tenant"].default_wr, (
        "le scenario suppose que le secteur propose autre chose que le defaut"
    )
    assert graphe["tenant"].default_wr == 5, "le defaut du tenant reste intact"
    assert graphe["config"].wr == 5, "la config creee n'a pas ete influencee"


# -- coherence entre la source Python et la taxonomie -------------------------
@pytest.mark.asyncio(loop_scope="function")
async def test_le_socle_python_couvre_la_taxonomie():
    """Garde-fou statique, sans base : aucun secteur oublie dans SOCLE_INITIAL.

    Le socle Python et le SQL de la migration 0004 sont volontairement distincts — une
    migration doit rester figee dans le temps. Ce test verifie au moins qu'aucun
    secteur n'est oublie cote Python.
    """
    assert set(SOCLE_INITIAL) == set(SECTEURS)
