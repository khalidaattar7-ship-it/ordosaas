"""Tests de ScheduleStateManager : partition figee / future autour de T_now."""
import pytest

from scheduling.components.schedule_state_manager import ScheduleStateManager
from scheduling.models.schedule import Schedule, ScheduleEntry, SetupEntry


@pytest.fixture
def manager():
    return ScheduleStateManager()


def _entry(job_id, machine_id, position, start, duration, setup=None):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine_id, position_in_job=position,
        start_time=start, end_time=start + duration, duration=duration, setup=setup,
    )


@pytest.fixture
def petit_schedule():
    """Planning jouet : J1 (M1 puis M2), J2 (M1)."""
    return Schedule(entries=[
        _entry("J1", "M1", 1, 0, 30),     # terminee a T_now=50
        _entry("J1", "M2", 2, 40, 20),    # en cours a T_now=50
        _entry("J2", "M1", 1, 60, 25),    # future a T_now=50
    ])


# -- critere d'acceptation principal : partition stricte --------------------
def test_partition_reconstitue_le_schedule_dorigine(manager, petit_schedule):
    state = manager.split(petit_schedule, t_now=50)
    reconstitue = state.frozen_entries + state.future_entries
    assert len(reconstitue) == len(petit_schedule.entries)
    # Comparaison par identite : ni perte, ni duplication, ni copie.
    assert {id(e) for e in reconstitue} == {id(e) for e in petit_schedule.entries}


def test_partition_reconstitue_le_planning_reel(manager, example_schedule):
    """Meme garantie sur l'instance d'exemple a 10 jobs, a plusieurs T_now."""
    for t_now in (0, 50, 150, 400, example_schedule.horizon + 10):
        state = manager.split(example_schedule, t_now=t_now)
        reconstitue = state.frozen_entries + state.future_entries
        assert len(reconstitue) == len(example_schedule.entries)
        assert {id(e) for e in reconstitue} == {id(e) for e in example_schedule.entries}


# -- regle de classement ----------------------------------------------------
def test_operation_terminee_est_figee(manager, petit_schedule):
    state = manager.split(petit_schedule, t_now=50)
    assert any(e.job_id == "J1" and e.machine_id == "M1" for e in state.frozen_entries)


def test_operation_seulement_entamee_est_figee(manager, petit_schedule):
    """start_time <= T_now < end_time : figee malgre tout, contrainte dure."""
    state = manager.split(petit_schedule, t_now=50)
    entamee = [e for e in state.frozen_entries if e.machine_id == "M2"]
    assert len(entamee) == 1
    assert entamee[0].start_time <= 50 < entamee[0].end_time
    assert entamee[0] not in state.future_entries


def test_operation_demarrant_exactement_a_t_now_est_figee(manager):
    """start_time == T_now est du cote fige (comparaison <=, pas <)."""
    schedule = Schedule(entries=[_entry("J1", "M1", 1, 50, 30)])
    state = manager.split(schedule, t_now=50)
    assert len(state.frozen_entries) == 1
    assert state.future_entries == []


def test_operation_demarrant_juste_apres_t_now_est_future(manager):
    schedule = Schedule(entries=[_entry("J1", "M1", 1, 51, 30)])
    state = manager.split(schedule, t_now=50)
    assert state.frozen_entries == []
    assert len(state.future_entries) == 1


def test_t_now_zero_ne_fige_que_les_operations_demarrant_a_zero(manager, petit_schedule):
    state = manager.split(petit_schedule, t_now=0)
    assert len(state.frozen_entries) == 1
    assert state.frozen_entries[0].start_time == 0


def test_t_now_apres_horizon_fige_tout(manager, petit_schedule):
    state = manager.split(petit_schedule, t_now=10_000)
    assert len(state.frozen_entries) == len(petit_schedule.entries)
    assert state.future_entries == []


def test_t_now_negatif_refuse(manager, petit_schedule):
    with pytest.raises(ValueError, match="T_now"):
        manager.split(petit_schedule, t_now=-1)


def test_schedule_vide(manager):
    state = manager.split(Schedule(), t_now=100)
    assert state.frozen_entries == []
    assert state.future_entries == []
    assert state.in_progress_entries == []


# -- proprietes derivees ----------------------------------------------------
def test_in_progress_exclut_les_operations_terminees(manager, petit_schedule):
    state = manager.split(petit_schedule, t_now=50)
    en_cours = state.in_progress_entries
    assert len(en_cours) == 1
    assert en_cours[0].machine_id == "M2"


def test_jobs_a_cheval_sur_t_now(manager):
    """J1 a une operation figee et une future : il est a cheval."""
    schedule = Schedule(entries=[
        _entry("J1", "M1", 1, 0, 30),
        _entry("J1", "M2", 2, 60, 20),
        _entry("J2", "M1", 1, 70, 25),
    ])
    state = manager.split(schedule, t_now=50)
    assert state.straddling_job_ids == {"J1"}
    assert state.frozen_job_ids == {"J1"}
    assert state.future_job_ids == {"J1", "J2"}


def test_charge_machine_figee_tient_compte_des_setups(manager):
    """Un setup fige qui deborde repousse la disponibilite de la machine."""
    setup = SetupEntry(from_job_id="J0", start_time=10, end_time=20, duration=10)
    schedule = Schedule(entries=[
        _entry("J1", "M1", 1, 20, 30, setup=setup),  # op finit a 50
        _entry("J2", "M2", 1, 0, 15),                # op finit a 15
    ])
    state = manager.split(schedule, t_now=60)
    assert state.last_frozen_end_per_machine() == {"M1": 50, "M2": 15}


def test_charge_machine_ignore_les_entrees_futures(manager, petit_schedule):
    state = manager.split(petit_schedule, t_now=50)
    loads = state.last_frozen_end_per_machine()
    assert loads["M1"] == 30  # J2 sur M1 est future, pas comptee
    assert loads["M2"] == 60
