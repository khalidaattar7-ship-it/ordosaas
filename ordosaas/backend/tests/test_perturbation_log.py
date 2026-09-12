"""
Persistance des perturbations traitees (Piste B, livrable 3).

Ces tests relisent une VRAIE base apres chaque ecriture — jamais seulement l'objet en
memoire, qui pourrait sembler correct sans que rien ne soit reellement persiste.
"""
import pytest
from sqlalchemy import select

from app.models.perturbation_event import TYPES_EVENEMENT, PerturbationEventLog
from app.perturbation_log import (
    journalise_evenement,
    resout_et_journalise,
    serialise_payload,
)
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.perturbation import PerturbationType, make_event
from scheduling.models.schedule import Schedule, ScheduleEntry
from tests.bdd_fixtures import cree_graphe_minimal, session, socle  # noqa: F401

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------
# Un atelier minuscule, suffisant pour que resolve_incremental ait a travailler
# --------------------------------------------------------------------------
def _atelier():
    entries = [
        ScheduleEntry(job_id="J1", machine_id="M1", position_in_job=1,
                      start_time=100, end_time=150, duration=50),
        ScheduleEntry(job_id="J2", machine_id="M1", position_in_job=1,
                      start_time=150, end_time=200, duration=50),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1)], deadline=900, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1)], deadline=900, weight=1.0),
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times={}, wr=1)
    return Schedule(entries=entries), instance


def _panne(t_now=50):
    return make_event("machine_breakdown", timestamp=t_now, machine_id="M1",
                      start_time=100, end_time=130)


# ==========================================================================
# Livrable 3 — la persistance
# ==========================================================================
async def test_les_taxonomies_restent_alignees():
    """Le CHECK SQL et l'enum du coeur scheduling doivent dire la meme chose.

    Ce sont deux declarations independantes des memes cinq types. Les laisser diverger
    produirait un evenement valide cote Python et refuse en base, ou l'inverse.
    """
    assert set(TYPES_EVENEMENT) == {t.value for t in PerturbationType}


async def test_un_evenement_traite_est_relu_depuis_la_base(socle):
    """Critere d'acceptation : on RELIT la base, pas l'objet en memoire."""
    graphe = await cree_graphe_minimal(socle, secteur="plasturgie")
    schedule, instance = _atelier()
    event = _panne()

    resolution, _ligne = await resout_et_journalise(
        socle, schedule=schedule, event=event, instance=instance,
        tenant_id=graphe["tenant"].id,
        base_resolution_id=graphe["resolution"].id,
        reported_by=graphe["user"].id,
    )
    await socle.commit()
    socle.expunge_all()  # rien ne doit venir du cache d'identite

    relues = (await socle.execute(select(PerturbationEventLog))).scalars().all()
    assert len(relues) == 1

    relue = relues[0]
    assert relue.event_type == "machine_breakdown"
    assert relue.tenant_id == graphe["tenant"].id
    assert relue.base_resolution_id == graphe["resolution"].id
    assert relue.reported_by == graphe["user"].id
    assert relue.created_at is not None, "horodatage d'ecriture manquant"
    assert relue.event_timestamp == 50, "T_now du planning conserve"
    assert resolution.schedule is not None, "la cascade a bien produit un planning"


async def test_le_payload_est_conserve_integralement(socle):
    """Le payload doit permettre de rejouer ou d'auditer l'evenement plus tard."""
    graphe = await cree_graphe_minimal(socle)
    event = _panne()

    await journalise_evenement(
        socle, event=event, tenant_id=graphe["tenant"].id,
        base_resolution_id=graphe["resolution"].id,
        reported_by=graphe["user"].id,
    )
    await socle.commit()
    socle.expunge_all()

    relue = (await socle.execute(select(PerturbationEventLog))).scalars().one()
    assert relue.payload == {
        "machine_id": "M1", "start_time": 100, "end_time": 130,
    }


async def test_un_payload_imbrique_est_serialise(socle):
    """Le job urgent porte des `Operation`, elles-memes dataclasses."""
    graphe = await cree_graphe_minimal(socle)
    event = make_event(
        "urgent_job", timestamp=50, job_id="URGENT",
        operations=[Operation("URGENT", "M1", 20, 1)], deadline=400, weight=9.0,
    )

    await journalise_evenement(
        socle, event=event, tenant_id=graphe["tenant"].id,
        base_resolution_id=graphe["resolution"].id,
        reported_by=graphe["user"].id,
    )
    await socle.commit()
    socle.expunge_all()

    relue = (await socle.execute(select(PerturbationEventLog))).scalars().one()
    assert relue.payload["job_id"] == "URGENT"
    assert relue.payload["operations"][0]["machine_id"] == "M1"
    assert relue.payload["operations"][0]["duration"] == 20


async def test_un_payload_non_dataclass_est_refuse():
    """Echec franc plutot qu'une ligne de journal inexploitable."""
    with pytest.raises(TypeError, match="non serialisable"):
        serialise_payload({"machine_id": "M1"})


async def test_le_coeur_scheduling_reste_sans_dependance_base():
    """Invariant d'architecture (D9), verrouille par un test.

    `scheduling/incremental.py` ne doit importer ni SQLAlchemy ni `app`. Si ce test
    tombe, c'est que le sens de la dependance s'est inverse : c'est le service qui
    appelle l'orchestrateur, jamais l'inverse.
    """
    import pathlib

    source = pathlib.Path("scheduling/incremental.py").read_text(encoding="utf-8")
    for interdit in ("sqlalchemy", "from app", "import app"):
        assert interdit not in source, (
            f"scheduling/incremental.py ne doit pas dependre de {interdit!r}"
        )
