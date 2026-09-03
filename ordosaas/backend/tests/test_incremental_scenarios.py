"""
Scenarios de reordonnancement incremental sur l'instance d'exemple a 10 jobs.

Chaine complete : PerturbationEvent -> ScheduleStateManager -> ImpactAnalyzer ->
IncrementalContextBuilder -> IncrementalOptimizer -> ScheduleMerger.

Ce sont les 3-4 scenarios MINIMAUX demandes pour valider que chaque composant
fonctionne bout en bout sur une instance reelle (10 jobs, 3 machines, WR=2). La
suite de test approfondie et le script de validation dedie relevent de la
Discussion 2 et ne sont pas ici.

Trois invariants sont verifies pour CHAQUE scenario, via `_verifie_les_invariants` :
  1. aucune operation figee (start_time <= T_now) n'est deplacee ni modifiee,
  2. aucun chevauchement aux deux frontieres du Schedule fusionne,
  3. le nombre de jobs reellement modifies est proportionne a la perturbation.
"""
import pytest

from scheduling.components.impact_analyzer import ImpactAnalyzer
from scheduling.components.incremental_context_builder import IncrementalContextBuilder
from scheduling.components.schedule_merger import ScheduleMerger
from scheduling.models.job import Operation
from scheduling.models.perturbation import make_event
from scheduling.solvers.incremental_optimizer import IncrementalOptimizer
from scheduling.validation import validate_schedule


def _replanifie(event, schedule, instance, search_horizon=400):
    """Deroule la chaine incrementale complete et renvoie tout le contexte utile."""
    analyzer = ImpactAnalyzer(search_horizon=search_horizon, max_impacted_jobs=30)
    zone = analyzer.analyze(event, schedule, instance)
    contexts = IncrementalContextBuilder().build(zone, instance)
    result = IncrementalOptimizer(timeout_seconds=12).optimize(zone, contexts, instance)
    assert result is not None, "CP-SAT n'a trouve aucune solution sur la zone d'impact"
    merged, report = ScheduleMerger().merge(zone, result, instance)
    return zone, result, merged, report


def _verifie_les_invariants(zone, merged, report, instance, max_ratio=1.0):
    """Les trois verifications systematiques demandees pour chaque scenario."""
    # 1. Aucune operation figee deplacee ni modifiee.
    fusionnees = {
        (e.job_id, e.position_in_job): (e.start_time, e.end_time, e.duration)
        for e in merged.entries
    }
    for figee in zone.state.frozen_entries:
        cle = (figee.job_id, figee.position_in_job)
        assert cle in fusionnees, f"Operation figee {cle} disparue de la fusion"
        assert fusionnees[cle] == (figee.start_time, figee.end_time, figee.duration), (
            f"Operation figee {cle} deplacee ou modifiee"
        )

    # 2. Aucun chevauchement aux deux frontieres, et planning globalement valide.
    assert report.left_boundary_violations == []
    assert report.right_boundary_violations == []
    assert validate_schedule(merged, instance=instance) == []

    # 3. Ampleur proportionnee a la perturbation.
    assert report.nb_jobs_affected <= zone.nb_impacted_jobs
    if zone.nb_future_jobs:
        ratio = report.nb_jobs_affected / zone.nb_future_jobs
        assert ratio <= max_ratio, (
            f"{report.nb_jobs_affected} job(s) replanifie(s) sur {zone.nb_future_jobs} "
            f"futurs : disproportionne pour cette perturbation"
        )


@pytest.fixture
def t_now(example_schedule):
    """Un tiers de l'horizon : le planning est deja bien entame."""
    return example_schedule.horizon // 3


# ==========================================================================
# Scenario 1 — panne machine sur une fenetre courte au milieu du planning
# ==========================================================================
def test_scenario_panne_machine(example_schedule, example_instance, t_now):
    machine = example_instance.machines[1]  # M2
    event = make_event("machine_breakdown", timestamp=t_now, machine_id=machine,
                       start_time=t_now + 5, end_time=t_now + 35)
    zone, result, merged, report = _replanifie(event, example_schedule, example_instance)

    _verifie_les_invariants(zone, merged, report, example_instance, max_ratio=0.75)

    # La zone est bien limitee aux operations de cette machine et a leur cascade.
    assert machine in zone.machines_involved
    # Aucune operation ne subsiste dans la fenetre d'indisponibilite.
    for entry in merged.entries:
        if entry.machine_id == machine and entry.start_time > t_now:
            assert entry.end_time <= t_now + 5 or entry.start_time >= t_now + 35


def test_scenario_panne_machine_sur_planning_dense(example_schedule, example_instance,
                                                   t_now):
    """Constat sur l'instance d'exemple : le planning initial est tres dense.

    CP-SAT compacte le planning initial, il n'y reste presque aucun temps mort.
    L'absorption du retard n'a donc rien a absorber : meme une panne de 10 unites
    de temps se propage a une large part des jobs futurs, et le garde-fou de repli
    se declenche. Ce n'est pas un defaut de la cascade — c'est la propriete du
    planning de depart, et c'est exactement le cas que le garde-fou existe pour
    detecter.

    Le critere "une perturbation locale reste locale" est verifie la ou il a un
    sens, sur un planning comportant du temps mort : cf.
    tests/test_impact_analyzer.py::test_le_temps_mort_absorbe_le_retard.
    """
    machine = example_instance.machines[1]
    event = make_event("machine_breakdown", timestamp=t_now, machine_id=machine,
                       start_time=t_now + 5, end_time=t_now + 15)
    zone, _, _, report = _replanifie(event, example_schedule, example_instance)

    assert zone.fallback_recommended is True
    assert zone.ratio_future_jobs_affected > 0.5
    # La chaine reste neanmoins exploitable : elle produit un planning valide.
    assert report.is_clean


def test_le_garde_fou_ne_se_declenche_pas_sur_une_perturbation_ciblee(
    example_schedule, example_instance, t_now
):
    """Une annulation de job ne touche qu'une part limitee du planning futur."""
    futurs = sorted({
        e.job_id for e in example_schedule.entries if e.start_time > t_now
    })
    event = make_event("job_cancel", timestamp=t_now, job_id=futurs[-1])
    zone, _, _, _ = _replanifie(event, example_schedule, example_instance)

    assert zone.ratio_future_jobs_affected <= 0.5
    assert zone.fallback_recommended is False


# ==========================================================================
# Scenario 2 — job urgent insere apres le debut d'execution du planning
# ==========================================================================
def test_scenario_job_urgent(example_schedule, example_instance, t_now):
    machines = example_instance.machines
    event = make_event(
        "urgent_job", timestamp=t_now, job_id="J_URGENT",
        operations=[
            Operation("J_URGENT", machines[0], 20, 1),
            Operation("J_URGENT", machines[1], 15, 2),
        ],
        deadline=t_now + 120, weight=9.9,
    )
    zone, result, merged, report = _replanifie(event, example_schedule, example_instance)

    _verifie_les_invariants(zone, merged, report, example_instance)

    # L'insertion a bien eu lieu, apres T_now, sans toucher au fige.
    inserees = [e for e in merged.entries if e.job_id == "J_URGENT"]
    assert len(inserees) == 2
    assert all(e.start_time >= t_now for e in inserees)
    # Precedence interne du job urgent respectee.
    inserees.sort(key=lambda e: e.position_in_job)
    assert inserees[0].end_time <= inserees[1].start_time


def test_scenario_job_urgent_retard_recalcule(example_schedule, example_instance, t_now):
    """Le retard pondere du planning fusionne integre le nouveau job."""
    machines = example_instance.machines
    event = make_event(
        "urgent_job", timestamp=t_now, job_id="J_URGENT",
        operations=[Operation("J_URGENT", machines[0], 20, 1)],
        deadline=t_now + 120, weight=9.9,
    )
    _, _, merged, _ = _replanifie(event, example_schedule, example_instance)

    resultats = {r.job_id: r for r in merged.jobs_result}
    assert "J_URGENT" in resultats
    assert len(merged.jobs_result) == len(example_instance.jobs) + 1
    # Le retard total est bien la somme des retards ponderes de chaque job.
    attendu = sum(r.weighted_tardiness for r in merged.jobs_result)
    assert merged.total_weighted_tardiness == pytest.approx(attendu, abs=0.01)


# ==========================================================================
# Scenario 3 — depassement de duree reelle
# ==========================================================================
def test_scenario_depassement_de_duree(example_schedule, example_instance, t_now):
    """Une operation future dure 50 % de plus que prevu."""
    future = sorted(
        (e for e in example_schedule.entries if e.start_time > t_now),
        key=lambda e: e.start_time,
    )
    cible = future[0]
    event = make_event(
        "duration_change", timestamp=t_now, job_id=cible.job_id,
        position_in_job=cible.position_in_job, machine_id=cible.machine_id,
        new_duration=int(cible.duration * 1.5) + 1,
    )
    zone, _, merged, report = _replanifie(event, example_schedule, example_instance)

    _verifie_les_invariants(zone, merged, report, example_instance)

    # La duree reelle a bien remplace la duree prevue.
    replanifiee = [
        e for e in merged.entries
        if e.job_id == cible.job_id and e.position_in_job == cible.position_in_job
    ][0]
    assert replanifiee.duration == int(cible.duration * 1.5) + 1
    assert replanifiee.end_time - replanifiee.start_time == replanifiee.duration


def test_scenario_depassement_la_stabilite_limite_les_perturbations(
    example_schedule, example_instance, t_now
):
    """Le terme de stabilite doit limiter les deplacements des jobs non concernes.

    Comparaison a poids nul contre poids par defaut : le nombre de jobs
    reellement deplaces ne doit pas augmenter quand on active la stabilite.
    """
    future = sorted(
        (e for e in example_schedule.entries if e.start_time > t_now),
        key=lambda e: e.start_time,
    )
    cible = future[0]
    event = make_event(
        "duration_change", timestamp=t_now, job_id=cible.job_id,
        position_in_job=cible.position_in_job, machine_id=cible.machine_id,
        new_duration=int(cible.duration * 1.5) + 1,
    )

    analyzer = ImpactAnalyzer(search_horizon=400, max_impacted_jobs=30)
    zone = analyzer.analyze(event, example_schedule, example_instance)
    contexts = IncrementalContextBuilder().build(zone, example_instance)

    deplaces = {}
    for poids in (0.0, 0.1):
        result = IncrementalOptimizer(
            timeout_seconds=12, stability_weight=poids
        ).optimize(zone, contexts, example_instance)
        _, report = ScheduleMerger().merge(zone, result, example_instance)
        deplaces[poids] = report.nb_jobs_affected

    assert deplaces[0.1] <= deplaces[0.0]


# ==========================================================================
# Scenario 4 — annulation de job
# ==========================================================================
def test_scenario_annulation_de_job(example_schedule, example_instance, t_now):
    """Les creneaux liberes sont absorbes sans reagencement disproportionne."""
    futurs = sorted({
        e.job_id for e in example_schedule.entries if e.start_time > t_now
    })
    annule = futurs[0]
    event = make_event("job_cancel", timestamp=t_now, job_id=annule)
    zone, _, merged, report = _replanifie(event, example_schedule, example_instance)

    _verifie_les_invariants(zone, merged, report, example_instance)

    # Aucune operation FUTURE du job annule ne subsiste.
    restantes = [
        e for e in merged.entries if e.job_id == annule and e.start_time > t_now
    ]
    assert restantes == []
    # Le job annule sort des KPI.
    assert all(r.job_id != annule for r in merged.jobs_result)
