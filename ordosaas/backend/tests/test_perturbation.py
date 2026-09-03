"""Tests de PerturbationEvent : les 5 types, la validation, le round-trip JSONB."""
import pytest

from scheduling.models.job import Operation
from scheduling.models.perturbation import (
    DurationChangePayload,
    JobCancelPayload,
    MachineBreakdownPayload,
    PerturbationEvent,
    PerturbationType,
    ResourceChangePayload,
    UrgentJobPayload,
    make_event,
)


def test_les_cinq_types_sont_couverts():
    """Les valeurs de l'enum sont exactement celles de la contrainte CHECK SQL."""
    assert {t.value for t in PerturbationType} == {
        "machine_breakdown",
        "urgent_job",
        "duration_change",
        "job_cancel",
        "resource_change",
    }


def test_type_inconnu_refuse():
    with pytest.raises(ValueError, match="Type de perturbation inconnu"):
        make_event("machine_explosion", timestamp=0, machine_id="M1")


def test_payload_incoherent_avec_le_type_refuse():
    with pytest.raises(TypeError, match="doit etre un MachineBreakdownPayload"):
        PerturbationEvent(
            event_type=PerturbationType.MACHINE_BREAKDOWN,
            timestamp=10,
            payload=JobCancelPayload(job_id="J1"),
        )


def test_type_accepte_aussi_la_chaine_brute():
    """La valeur venue de la colonne VARCHAR est normalisee en enum."""
    event = PerturbationEvent(
        event_type="job_cancel",
        timestamp=42,
        payload=JobCancelPayload(job_id="J3"),
    )
    assert event.event_type is PerturbationType.JOB_CANCEL


def test_affected_entities_deduit_du_payload():
    event = make_event("machine_breakdown", timestamp=50, machine_id="M2",
                       start_time=120, end_time=180)
    assert event.affected_entities == ["M2"]


def test_affected_entities_explicite_prime():
    event = make_event("machine_breakdown", timestamp=50,
                       affected_entities=["M2", "J4"],
                       machine_id="M2", start_time=120, end_time=180)
    assert event.affected_entities == ["M2", "J4"]


# -- validations par payload ------------------------------------------------
def test_panne_machine_fenetre_vide_refusee():
    with pytest.raises(ValueError, match="strictement superieur"):
        MachineBreakdownPayload(machine_id="M2", start_time=120, end_time=120)


def test_job_urgent_sans_operation_refuse():
    with pytest.raises(ValueError, match="au moins une operation"):
        UrgentJobPayload(job_id="J11", operations=[], deadline=300, weight=9.0)


def test_job_urgent_operation_rattachee_a_un_autre_job_refusee():
    with pytest.raises(ValueError, match="rattachee a J9"):
        UrgentJobPayload(
            job_id="J11",
            operations=[Operation("J9", "M1", 20, 1)],
            deadline=300,
            weight=9.0,
        )


def test_duration_change_position_zero_refusee():
    with pytest.raises(ValueError, match="1-indexe"):
        DurationChangePayload(job_id="J1", position_in_job=0, machine_id="M1",
                              new_duration=50)


def test_duration_change_duree_nulle_refusee():
    with pytest.raises(ValueError, match="new_duration"):
        DurationChangePayload(job_id="J1", position_in_job=1, machine_id="M1",
                              new_duration=0)


def test_resource_change_wr_zero_accepte():
    """WR = 0 est legitime : plus aucun setup possible sur la fenetre."""
    payload = ResourceChangePayload(new_wr=0, start_time=100, end_time=200)
    assert payload.new_wr == 0


def test_resource_change_wr_negatif_refuse():
    with pytest.raises(ValueError, match="new_wr"):
        ResourceChangePayload(new_wr=-1, start_time=100, end_time=200)


def test_timestamp_negatif_refuse():
    with pytest.raises(ValueError, match="timestamp"):
        make_event("job_cancel", timestamp=-1, job_id="J1")


# -- serialisation vers la colonne payload JSONB ----------------------------
@pytest.mark.parametrize("event", [
    make_event("machine_breakdown", timestamp=100, machine_id="M2",
               start_time=120, end_time=180),
    make_event("urgent_job", timestamp=100, job_id="J11",
               operations=[Operation("J11", "M1", 20, 1), Operation("J11", "M3", 15, 2)],
               deadline=300, weight=9.5),
    make_event("duration_change", timestamp=100, job_id="J1",
               position_in_job=2, machine_id="M2", new_duration=40),
    make_event("job_cancel", timestamp=100, job_id="J7"),
    make_event("resource_change", timestamp=100, new_wr=1,
               start_time=150, end_time=250),
])
def test_round_trip_json(event):
    """to_dict() / from_dict() est un aller-retour sans perte pour les 5 types."""
    reconstruit = PerturbationEvent.from_dict(event.to_dict())
    assert reconstruit == event


def test_to_dict_est_serialisable_json():
    import json

    event = make_event("urgent_job", timestamp=100, job_id="J11",
                       operations=[Operation("J11", "M1", 20, 1)],
                       deadline=300, weight=9.5)
    data = event.to_dict()
    json.dumps(data)  # ne doit pas lever
    assert data["event_type"] == "urgent_job"
    assert data["payload"]["operations"][0]["machine_id"] == "M1"
