"""Tests du garde-fou de repli : seuil configurable, signalement, non-routage."""
import inspect

import pytest

from scheduling.components.impact_analyzer import (
    DEFAULT_FALLBACK_THRESHOLD,
    ImpactAnalyzer,
    IncrementalNotSuitableError,
)
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.perturbation import make_event
from scheduling.models.schedule import Schedule, ScheduleEntry


def _entry(job_id, machine_id, position, start, duration):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine_id, position_in_job=position,
        start_time=start, end_time=start + duration, duration=duration,
    )


@pytest.fixture
def atelier_serre():
    """Quatre jobs enchaines sans temps mort sur M1 : le retard traverse tout."""
    entries = [_entry(f"J{i}", "M1", 1, 100 + 50 * i, 50) for i in range(4)]
    jobs = [
        Job(id=f"J{i}", operations=[Operation(f"J{i}", "M1", 50, 1)],
            deadline=1000, weight=1.0)
        for i in range(4)
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times={}, wr=1)
    return Schedule(entries=entries), instance


# -- le seuil est configurable, pas code en dur -----------------------------
def test_seuil_par_defaut_a_50_pourcent():
    assert DEFAULT_FALLBACK_THRESHOLD == 0.5
    assert ImpactAnalyzer().fallback_threshold == 0.5


def test_seuil_configurable(atelier_serre):
    """Le meme evenement passe ou non le garde-fou selon le seuil choisi."""
    schedule, instance = atelier_serre
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=200)

    tolerant = ImpactAnalyzer(search_horizon=10_000, fallback_threshold=1.0)
    severe = ImpactAnalyzer(search_horizon=10_000, fallback_threshold=0.1)

    assert tolerant.analyze(event, schedule, instance).fallback_recommended is False
    assert severe.analyze(event, schedule, instance).fallback_recommended is True


def test_seuil_invalide_refuse():
    with pytest.raises(ValueError, match="fallback_threshold"):
        ImpactAnalyzer(fallback_threshold=0)
    with pytest.raises(ValueError, match="fallback_threshold"):
        ImpactAnalyzer(fallback_threshold=1.5)


# -- signalement ------------------------------------------------------------
def test_une_perturbation_massive_est_signalee(atelier_serre):
    """Tous les jobs futurs touches : l'incremental n'a plus de sens."""
    schedule, instance = atelier_serre
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=400)
    zone = ImpactAnalyzer(search_horizon=10_000).analyze(event, schedule, instance)

    assert zone.ratio_future_jobs_affected > 0.5
    assert zone.fallback_recommended is True


def test_une_perturbation_locale_nest_pas_signalee():
    """Un incident absorbe par le planning reste du ressort de l'incremental."""
    entries = [
        _entry("J0", "M1", 1, 100, 50),
        _entry("J1", "M1", 1, 1000, 50),
        _entry("J2", "M1", 1, 2000, 50),
        _entry("J3", "M1", 1, 3000, 50),
    ]
    jobs = [
        Job(id=f"J{i}", operations=[Operation(f"J{i}", "M1", 50, 1)],
            deadline=5000, weight=1.0)
        for i in range(4)
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times={}, wr=1)
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone = ImpactAnalyzer(search_horizon=10_000).analyze(
        event, Schedule(entries=entries), instance
    )

    assert zone.ratio_future_jobs_affected <= 0.5
    assert zone.fallback_recommended is False


def test_check_suitability_leve_une_exception_dediee(atelier_serre):
    schedule, instance = atelier_serre
    analyzer = ImpactAnalyzer(search_horizon=10_000, fallback_threshold=0.1)
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=200)
    zone = analyzer.analyze(event, schedule, instance)

    with pytest.raises(IncrementalNotSuitableError) as exc:
        analyzer.check_suitability(zone)

    assert exc.value.threshold == 0.1
    assert exc.value.zone is zone
    assert "relancer une resolution complete" in str(exc.value)


def test_check_suitability_ne_leve_pas_sur_zone_raisonnable(atelier_serre):
    schedule, instance = atelier_serre
    analyzer = ImpactAnalyzer(search_horizon=10_000, fallback_threshold=1.0)
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=200)
    zone = analyzer.analyze(event, schedule, instance)

    analyzer.check_suitability(zone)  # ne doit pas lever
    assert analyzer.is_suitable(zone) is True


def test_analyze_ne_leve_jamais_de_lui_meme(atelier_serre):
    """Le drapeau signale, il ne bloque pas : l'appelant reste maitre."""
    schedule, instance = atelier_serre
    analyzer = ImpactAnalyzer(search_horizon=10_000, fallback_threshold=0.01)
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=200)

    zone = analyzer.analyze(event, schedule, instance)  # ne doit pas lever
    assert zone.fallback_recommended is True


# -- non-routage : explicitement hors perimetre de cette session ------------
def test_le_dispatcher_ne_route_pas_encore_vers_lincremental():
    """Le routage reel est laisse pour une session ulterieure (H5).

    Ce test verrouille l'absence de routage : s'il tombe, c'est que quelqu'un a
    branche SolverDispatcher, et il faudra alors retirer H5 de
    docs/CONTEXTE_ET_DECISIONS.md plutot que de contourner ce test.
    """
    from scheduling import dispatcher

    source = inspect.getsource(dispatcher)
    assert "IncrementalOptimizer" not in source
    assert "IncrementalNotSuitableError" not in source
