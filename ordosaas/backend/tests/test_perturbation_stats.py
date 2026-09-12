"""
Analyse des causes de replanification par tenant (Piste B, livrable 4).

C'est la MESURE, pas la boucle d'ajustement : ces tests verifient que la repartition
rendue est juste, pas qu'elle declenche quoi que ce soit. Recalibrer un socle sectoriel
a partir de ce constat est une decision distincte, deliberement non automatisee.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.perturbation_event import TYPES_EVENEMENT
from app.perturbation_log import journalise_evenement
from app.perturbation_stats import repartition_des_causes
from app.sectors import defauts_pour_tenant
from scheduling.models.job import Operation
from scheduling.models.perturbation import make_event
from tests.bdd_fixtures import cree_graphe_minimal, session, socle  # noqa: F401

pytestmark = pytest.mark.asyncio


def _panne(t_now=50):
    return make_event("machine_breakdown", timestamp=t_now, machine_id="M1",
                      start_time=100, end_time=130)


async def _journalise_types(session_bdd, graphe, types):
    """Journalise une perturbation par type demande."""
    fabriques = {
        "machine_breakdown": lambda: _panne(),
        "urgent_job": lambda: make_event(
            "urgent_job", timestamp=50, job_id="U",
            operations=[Operation("U", "M1", 10, 1)], deadline=400, weight=5.0),
        "duration_change": lambda: make_event(
            "duration_change", timestamp=50, job_id="J1",
            position_in_job=1, machine_id="M1", new_duration=70),
        "job_cancel": lambda: make_event("job_cancel", timestamp=50, job_id="J2"),
        "resource_change": lambda: make_event(
            "resource_change", timestamp=50, start_time=100, end_time=200, new_wr=1),
    }
    for t in types:
        await journalise_evenement(
            session_bdd, event=fabriques[t](), tenant_id=graphe["tenant"].id,
            base_resolution_id=graphe["resolution"].id,
            reported_by=graphe["user"].id,
        )
    await session_bdd.commit()


async def test_la_repartition_est_chiffree_correctement(socle):
    """Critere d'acceptation : plusieurs types melanges, repartition exacte."""
    graphe = await cree_graphe_minimal(socle)
    await _journalise_types(socle, graphe, [
        "machine_breakdown", "machine_breakdown", "machine_breakdown",
        "urgent_job", "job_cancel",
    ])

    r = await repartition_des_causes(socle, graphe["tenant"].id)

    assert r.total == 5
    assert r.comptes["machine_breakdown"] == 3
    assert r.comptes["urgent_job"] == 1
    assert r.comptes["job_cancel"] == 1
    assert r.pourcentages["machine_breakdown"] == 60.0
    assert r.pourcentages["urgent_job"] == 20.0
    assert r.cause_dominante == "machine_breakdown"


async def test_les_cinq_types_sont_toujours_presents(socle):
    """Un type absent vaut zero, il ne disparait pas du resultat.

    L'absence d'un type est une information : un atelier qui n'a jamais de job urgent
    en dit autant qu'un atelier qui n'a que ca.
    """
    graphe = await cree_graphe_minimal(socle)
    await _journalise_types(socle, graphe, ["machine_breakdown"])

    r = await repartition_des_causes(socle, graphe["tenant"].id)

    assert set(r.comptes) == set(TYPES_EVENEMENT)
    assert r.comptes["urgent_job"] == 0
    assert r.pourcentages["urgent_job"] == 0.0


async def test_un_tenant_sans_historique_repond_explicitement(socle):
    """Ni erreur, ni division par zero silencieuse : un constat vide."""
    graphe = await cree_graphe_minimal(socle)

    r = await repartition_des_causes(socle, graphe["tenant"].id)

    assert r.sans_historique is True
    assert r.total == 0
    assert r.pourcentages == {}, "aucun pourcentage ne peut etre calcule sur zero"
    assert r.cause_dominante is None
    assert set(r.comptes) == set(TYPES_EVENEMENT)
    assert all(n == 0 for n in r.comptes.values())


async def test_la_repartition_est_cloisonnee_par_tenant(socle):
    """Le journal d'un tenant ne doit jamais fuir dans l'analyse d'un autre."""
    a = await cree_graphe_minimal(socle, secteur="plasturgie")
    b = await cree_graphe_minimal(socle, secteur="textile")
    await _journalise_types(socle, a, ["machine_breakdown", "machine_breakdown"])
    await _journalise_types(socle, b, ["urgent_job"])

    ra = await repartition_des_causes(socle, a["tenant"].id)
    rb = await repartition_des_causes(socle, b["tenant"].id)

    assert ra.total == 2 and ra.cause_dominante == "machine_breakdown"
    assert rb.total == 1 and rb.cause_dominante == "urgent_job"


async def test_la_fenetre_temporelle_filtre_reellement(socle):
    """Les bornes portent sur `created_at`, l'instant d'ecriture."""
    graphe = await cree_graphe_minimal(socle)
    await _journalise_types(socle, graphe, ["machine_breakdown", "urgent_job"])

    maintenant = datetime.now(timezone.utc)
    avant = maintenant - timedelta(days=1)
    apres = maintenant + timedelta(days=1)

    assert (await repartition_des_causes(socle, graphe["tenant"].id,
                                         depuis=avant)).total == 2
    assert (await repartition_des_causes(socle, graphe["tenant"].id,
                                         depuis=apres)).total == 0
    assert (await repartition_des_causes(socle, graphe["tenant"].id,
                                         jusqua=avant)).total == 0
    assert (await repartition_des_causes(socle, graphe["tenant"].id,
                                         depuis=avant, jusqua=apres)).total == 2


async def test_la_cause_dominante_est_deterministe_en_cas_degalite(socle):
    """Une egalite ne doit pas dependre de l'ordre rendu par la base."""
    graphe = await cree_graphe_minimal(socle)
    await _journalise_types(socle, graphe, ["urgent_job", "job_cancel"])

    r = await repartition_des_causes(socle, graphe["tenant"].id)

    assert r.comptes["urgent_job"] == r.comptes["job_cancel"] == 1
    # `urgent_job` precede `job_cancel` dans TYPES_EVENEMENT.
    assert r.cause_dominante == "urgent_job"


# ==========================================================================
# Validation manuelle — scenario calcule a la main avant execution
# ==========================================================================
async def test_scenario_calcule_a_la_main_le_journal_contredit_le_secteur(socle):
    """Scenario construit et CALCULE A LA MAIN, conserve comme test permanent.

    Pratique etablie du projet (section Approche & patterns) : valider contre un cas
    reel calcule a la main avant de clore, pas seulement par les tests unitaires.

    LE SCENARIO, et son calcul prealable :

        Un tenant declare le secteur `cablage_auto`. Le socle PROPOSE donc
        stability_weight = 0.3, sur l'HYPOTHESE que les insertions (jobs urgents JIS)
        dominent.

        On journalise ensuite 10 perturbations reellement traitees :

            machine_breakdown  x6      duration_change  x2
            urgent_job         x1      job_cancel       x1
            resource_change    x0

        Repartition attendue, calculee a la main :

            total = 6 + 2 + 1 + 1 + 0 = 10
            machine_breakdown  6/10 = 60.0 %      duration_change 2/10 = 20.0 %
            urgent_job         1/10 = 10.0 %      job_cancel      1/10 = 10.0 %
            resource_change    0/10 =  0.0 %
            cause dominante    machine_breakdown

    CE QUE CELA DEMONTRE : l'hypothese sectorielle disait « insertions dominantes ».
    Le journal dit 60 % d'aleas SUBIS pour 10 % d'insertions — elle est CONTREDITE.

    C'est exactement la boucle voulue : le secteur est un point de depart, les logs
    sont la verite. La session produit la mesure ; le recalibrage reste une decision
    distincte et non automatisee.
    """
    fabriques = {
        "machine_breakdown": _panne,
        "duration_change": lambda: make_event(
            "duration_change", timestamp=50, job_id="J1",
            position_in_job=1, machine_id="M1", new_duration=70),
        "urgent_job": lambda: make_event(
            "urgent_job", timestamp=50, job_id="U",
            operations=[Operation("U", "M1", 10, 1)], deadline=400, weight=5.0),
        "job_cancel": lambda: make_event("job_cancel", timestamp=50, job_id="J2"),
    }
    attendu = {
        "machine_breakdown": (6, 60.0), "duration_change": (2, 20.0),
        "urgent_job": (1, 10.0), "job_cancel": (1, 10.0),
        "resource_change": (0, 0.0),
    }

    graphe = await cree_graphe_minimal(socle, secteur="cablage_auto")
    await socle.commit()

    # L'hypothese sectorielle, avant toute donnee reelle.
    propose = await defauts_pour_tenant(socle, graphe["tenant"])
    assert propose["stability_weight"] == 0.3, (
        "le scenario suppose que cablage_auto parie sur les insertions"
    )

    for type_evt, (nombre, _) in attendu.items():
        for _ in range(nombre):
            await journalise_evenement(
                socle, event=fabriques[type_evt](),
                tenant_id=graphe["tenant"].id,
                base_resolution_id=graphe["resolution"].id,
                reported_by=graphe["user"].id,
            )
    await socle.commit()
    socle.expunge_all()

    r = await repartition_des_causes(socle, graphe["tenant"].id)

    assert r.total == 10
    for type_evt, (nombre, pourcentage) in attendu.items():
        assert r.comptes[type_evt] == nombre, type_evt
        assert r.pourcentages[type_evt] == pourcentage, type_evt
    assert r.cause_dominante == "machine_breakdown"

    # Le constat qui justifie toute l'instrumentation : la donnee contredit le socle.
    assert r.pourcentages["machine_breakdown"] > r.pourcentages["urgent_job"] * 5, (
        "les aleas subis dominent largement, contre l'hypothese du secteur"
    )
