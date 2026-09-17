"""Le setup du contexte gauche n'est paye que par le PREMIER job de la machine.

Verrouille l'amelioration de qualite differee depuis D12 : le dernier job fige
d'une machine ne precede immediatement qu'UN seul job, celui que le circuit place
en premier. Le setup correspondant se rattache donc au litteral de l'arc
`depot -> job`, et non plus a tous les jobs de la machine.

Les tests portent sur la propriete OBSERVABLE — un job non premier n'est plus borne
par `charge + setup(dernier_fige, lui)` — et non sur la technique employee.

Cas construit a la main, ou PLUSIEURS jobs pourraient plausiblement etre le premier :

    Machine M1, charge figee 50, dernier job fige JF.
    setup(JF -> A) = 0, setup(JF -> B) = 100, setup(JF -> C) = 100.
    setups internes A/B/C tous nuls.

    Ancien comportement : A >= 50, B >= 150, C >= 150   -> makespan 170
    Nouveau comportement : A premier, puis B et C libres -> makespan 80

Le choix de A comme premier n'est pas impose : il est le seul dont le setup entrant
depuis JF soit nul, donc le seul que l'optimum puisse placer en tete.
"""
import pytest

from scheduling.components.impact_analyzer import ImpactAnalyzer
from scheduling.components.incremental_context_builder import IncrementalContextBuilder
from scheduling.models.context import BoundaryContext
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.perturbation import make_event
from scheduling.models.schedule import Schedule, ScheduleEntry
from scheduling.solvers.cpsat_solver import CPSATSolver
from scheduling.solvers.incremental_optimizer import IncrementalOptimizer
from tests.test_setups_payes import transitions_non_payees

CHARGE = 50
SETUP_LOURD = 100


def _solveur():
    return CPSATSolver(timeout_seconds=10, num_search_workers=1, random_seed=42)


@pytest.fixture
def instance_trois_candidats():
    """Trois jobs sur M1 ; seul A a un setup entrant nul depuis le job fige JF."""
    # Echeances SERREES : sans retard a minimiser, toutes les solutions faisables
    # seraient egalement optimales et CP-SAT en rendrait une arbitraire — le test
    # verrouillerait alors un choix du solveur, pas un comportement du modele.
    jobs = [
        Job(id=j, operations=[Operation(j, "M1", 10, 1)], deadline=60, weight=1.0)
        for j in ("A", "B", "C")
    ]
    setups = {
        ("JF", "A", "M1"): 0,
        ("JF", "B", "M1"): SETUP_LOURD,
        ("JF", "C", "M1"): SETUP_LOURD,
    }
    return ProblemInstance(jobs=jobs, machines=["M1"], setup_times=setups, wr=2)


@pytest.fixture
def contexte_gauche():
    return BoundaryContext(
        last_job_per_machine={"M1": "JF"}, active_setups=[], pending_jobs=["JF"],
        machine_loads={"M1": CHARGE},
    )


def _debuts(schedule):
    return {e.job_id: e.start_time for e in schedule.entries}


# ==========================================================================
# CPSATSolver.solve_with_context — code partage (resolution directe, LNS,
# InterWindowOptimizer)
# ==========================================================================
def test_cpsat_seul_le_premier_job_paie_le_setup_du_contexte_gauche(
    instance_trois_candidats, contexte_gauche
):
    schedule = _solveur().solve_with_context(
        instance_trois_candidats, contexte_gauche, None
    )
    assert schedule is not None
    debuts = _debuts(schedule)

    premier = min(debuts, key=debuts.get)
    setup_du = instance_trois_candidats.get_setup("JF", premier, "M1")
    assert debuts[premier] >= CHARGE + setup_du, (
        "le job reellement premier doit payer son setup depuis le job fige"
    )

    # Le coeur du correctif : les AUTRES jobs ne sont plus artificiellement bornes.
    liberes = [
        j for j, d in debuts.items()
        if j != premier
        and d < CHARGE + instance_trois_candidats.get_setup("JF", j, "M1")
    ]
    assert liberes, (
        f"aucun job libere : debuts={debuts}. Les jobs non premiers subissent "
        f"encore le setup du contexte gauche."
    )


def test_cpsat_la_relaxation_ne_casse_aucun_setup_du(
    instance_trois_candidats, contexte_gauche
):
    """Surete par transitivite : tous les setups dus restent payes."""
    schedule = _solveur().solve_with_context(
        instance_trois_candidats, contexte_gauche, None
    )
    assert transitions_non_payees(schedule, instance_trois_candidats) == []
    # Aucun job ne peut demarrer avant que la machine soit reellement liberee.
    assert all(e.start_time >= CHARGE for e in schedule.entries)


def test_cpsat_le_makespan_passe_sous_la_borne_de_lancien_modele(
    instance_trois_candidats, contexte_gauche
):
    """L'ancien modele ne pouvait pas descendre sous 170 ; le nouveau le doit."""
    schedule = _solveur().solve_with_context(
        instance_trois_candidats, contexte_gauche, None
    )
    fin = max(e.end_time for e in schedule.entries)
    borne_ancien_modele = CHARGE + SETUP_LOURD + 10 + 10  # B et C pas avant 150
    assert fin < borne_ancien_modele, (
        f"makespan {fin}, la borne de l'ancien modele etait {borne_ancien_modele}"
    )


def test_cpsat_un_seul_job_sur_la_machine_reste_contraint():
    """Sans circuit (moins de deux jobs), la contrainte inconditionnelle est exacte."""
    instance = ProblemInstance(
        jobs=[Job(id="B", operations=[Operation("B", "M1", 10, 1)],
                  deadline=60, weight=1.0)],
        machines=["M1"], setup_times={("JF", "B", "M1"): SETUP_LOURD}, wr=2,
    )
    contexte = BoundaryContext(
        last_job_per_machine={"M1": "JF"}, active_setups=[], pending_jobs=["JF"],
        machine_loads={"M1": CHARGE},
    )
    schedule = _solveur().solve_with_context(instance, contexte, None)
    assert schedule.entries[0].start_time >= CHARGE + SETUP_LOURD


def test_cpsat_nemet_plus_de_setup_fantome_depuis_le_job_fige(
    instance_trois_candidats, contexte_gauche
):
    """Seul le job premier peut porter un SetupEntry venant du contexte gauche.

    Avant correction, tout job sans setup de zone entrant se voyait crediter un
    setup depuis le dernier job fige — y compris un job dont le predecesseur a
    simplement un setup nul, cas qui ne produit aucune entree dans `setup_vars`.
    """
    schedule = _solveur().solve_with_context(
        instance_trois_candidats, contexte_gauche, None
    )
    debuts = _debuts(schedule)
    premier = min(debuts, key=debuts.get)
    depuis_fige = [
        e.job_id for e in schedule.entries
        if e.setup is not None and e.setup.from_job_id == "JF"
    ]
    assert set(depuis_fige) <= {premier}, (
        f"setup fantome depuis JF porte par {depuis_fige}, premier={premier}"
    )


# ==========================================================================
# IncrementalOptimizer — modele dedie (D2), meme convention
# ==========================================================================
def _entry(job_id, machine_id, position, start, duration):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine_id, position_in_job=position,
        start_time=start, end_time=start + duration, duration=duration, setup=None,
    )


@pytest.fixture
def atelier_incremental():
    """JF fige sur M1 [40-50] ; A, B, C a replanifier apres T_now.

    Les trois sont serres derriere la panne pour qu'ils entrent TOUS dans la zone
    d'impact : c'est la condition pour que plusieurs jobs puissent plausiblement
    etre le premier apres le contexte gauche.
    """
    entries = [
        _entry("JF", "M1", 1, 40, 10),
        _entry("A", "M1", 1, 60, 10),
        _entry("B", "M1", 1, 75, 10),
        _entry("C", "M1", 1, 90, 10),
    ]
    jobs = [
        Job(id=j, operations=[Operation(j, "M1", 10, 1)], deadline=70, weight=1.0)
        for j in ("JF", "A", "B", "C")
    ]
    setups = {
        ("JF", "A", "M1"): 0,
        ("JF", "B", "M1"): SETUP_LOURD,
        ("JF", "C", "M1"): SETUP_LOURD,
    }
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times=setups, wr=2)
    return Schedule(entries=entries), instance


def test_incremental_seul_le_premier_job_paie_le_setup_du_contexte_gauche(
    atelier_incremental
):
    schedule, instance = atelier_incremental
    event = make_event("machine_breakdown", timestamp=55, machine_id="M1",
                       start_time=55, end_time=105)
    zone = ImpactAnalyzer(search_horizon=10_000, max_impacted_jobs=50).analyze(
        event, schedule, instance
    )
    contexts = IncrementalContextBuilder().build(zone, instance)
    assert {e.job_id for e in zone.impacted_entries} == {"A", "B", "C"}, (
        f"le cas suppose les trois jobs dans la zone : "
        f"{[e.job_id for e in zone.impacted_entries]}"
    )
    assert contexts.left.last_job_per_machine.get("M1") == "JF", (
        f"le cas de test suppose JF comme contexte gauche : {contexts.left}"
    )

    result = IncrementalOptimizer(timeout_seconds=10, stability_weight=0.0).optimize(
        zone, contexts, instance
    )
    assert result is not None
    debuts = _debuts(result.schedule)
    charge = contexts.left.machine_loads.get("M1", 0)

    premier = min(debuts, key=debuts.get)
    assert debuts[premier] >= charge + instance.get_setup("JF", premier, "M1")

    liberes = [
        j for j, d in debuts.items()
        if j != premier and d < charge + instance.get_setup("JF", j, "M1")
    ]
    assert liberes, (
        f"aucun job libere : debuts={debuts}, charge={charge}. Les jobs non "
        f"premiers subissent encore le setup du contexte gauche."
    )
