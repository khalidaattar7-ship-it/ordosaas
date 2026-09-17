"""Scenario construit et calcule A LA MAIN, exercant les deux correctifs du
2026-09-17 simultanement : l'arc du depot (D16) et la reservation WR (D17).

Le deroule attendu a ete calcule AVANT execution, conformement a la pratique du
projet ("Valider contre un cas construit et calcule a la main avant de clore").

ATELIER
    M1, M2. WR = 1 — UN SEUL technicien, c'est ce qui rend la Cumulative mordante.
    Contexte gauche : JF fige sur M1, JG fige sur M2, charge 100 des deux cotes.

    Job  Machine  Duree  Echeance  Poids
    A    M1       10     110       1
    B    M1       10     130       1
    C    M2       10     130       1

    Setups : JF->A = 0    JF->B = 30    A->B = 5    B->A = 40    JG->C = 20

CALCUL A LA MAIN
    1. Sur M1, l'ordre A puis B domine : 0 + 5 contre 30 + 40 pour l'ordre inverse.
    2. C ne peut pas finir avant 130 : charge 100 + setup 20 + duree 10. Son retard
       minimal est donc nul, et il n'est atteint qu'en placant JG->C des t=100.
    3. WR = 1 : les setups JG->C (20) et A->B (5) ne peuvent pas se chevaucher.
       Deux placements seulement :
         a) A->B d'abord [110,115], B [115,125] a l'heure, mais JG->C repousse a
            [115,135] et C finit a 145 -> retard 15.
         b) JG->C d'abord [100,120], C [120,130] a l'heure ; A->B [120,125],
            B [125,135] -> retard 5.
    4. L'optimum est donc (b), TWT = 5.

DEROULE ATTENDU
    A : [100,110]  sans setup (JF->A vaut 0)
    C : [120,130]  setup JG->C [100,120]
    B : [125,135]  setup A->B   [120,125]
    TWT = 5

CE QUE LE SCENARIO DEMONTRE
    - Arc du depot : B ne paie PAS setup(JF,B) = 30. Sous l'ancien modele il aurait
      du demarrer a 130 au plus tot, pour un retard de 10 au lieu de 5.
    - Reservation WR : sous l'ancien modele, JG->C n'etait aucun intervalle. Le
      solveur aurait place A->B en [110,115] par-dessus le SetupEntry JG->C
      [100,120] qu'il emettait pourtant — deux setups simultanes pour WR = 1, donc
      un planning que le validateur canonique REJETTE.
"""
import pytest

from scheduling.models.context import BoundaryContext
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.solvers.cpsat_solver import CPSATSolver
from scheduling.validation import validate_schedule

CHARGE = 100

# Le deroule calcule a la main, avant execution.
ATTENDU = {
    "A": {"debut": 100, "fin": 110, "setup": None},
    "C": {"debut": 120, "fin": 130, "setup": ("JG", 100, 120, 20)},
    "B": {"debut": 125, "fin": 135, "setup": ("A", 120, 125, 5)},
}
TWT_ATTENDU = 5.0


@pytest.fixture
def atelier():
    jobs = [
        Job(id="A", operations=[Operation("A", "M1", 10, 1)], deadline=110, weight=1.0),
        Job(id="B", operations=[Operation("B", "M1", 10, 1)], deadline=130, weight=1.0),
        Job(id="C", operations=[Operation("C", "M2", 10, 1)], deadline=130, weight=1.0),
    ]
    setups = {
        ("JF", "A", "M1"): 0,
        ("JF", "B", "M1"): 30,
        ("A", "B", "M1"): 5,
        ("B", "A", "M1"): 40,
        ("JG", "C", "M2"): 20,
    }
    instance = ProblemInstance(
        jobs=jobs, machines=["M1", "M2"], setup_times=setups, wr=1,
    )
    contexte = BoundaryContext(
        last_job_per_machine={"M1": "JF", "M2": "JG"}, active_setups=[],
        pending_jobs=["JF", "JG"], machine_loads={"M1": CHARGE, "M2": CHARGE},
    )
    return instance, contexte


@pytest.fixture
def resolu(atelier):
    instance, contexte = atelier
    schedule = CPSATSolver(
        timeout_seconds=30, num_search_workers=1, random_seed=42,
    ).solve_with_context(instance, contexte, None)
    assert schedule is not None, "aucune solution trouvee"
    return schedule, instance


def test_le_deroule_est_exactement_celui_calcule_a_la_main(resolu):
    schedule, _instance = resolu
    obtenu = {}
    for entry in schedule.entries:
        setup = None
        if entry.setup and entry.setup.duration > 0:
            setup = (entry.setup.from_job_id, entry.setup.start_time,
                     entry.setup.end_time, entry.setup.duration)
        obtenu[entry.job_id] = {
            "debut": entry.start_time, "fin": entry.end_time, "setup": setup,
        }
    assert obtenu == ATTENDU


def test_le_twt_est_celui_calcule_a_la_main(resolu):
    schedule, _instance = resolu
    assert schedule.total_weighted_tardiness == TWT_ATTENDU


def test_le_planning_est_valide(resolu):
    schedule, instance = resolu
    assert validate_schedule(schedule, instance=instance) == []


def test_b_ne_paie_pas_le_setup_du_contexte_gauche(resolu):
    """Arc du depot : B n'est pas premier, setup(JF,B) = 30 ne le concerne pas.

    Sous l'ancien modele B aurait demarre a 130 au plus tot (charge 100 + 30),
    pour un retard de 10 au lieu de 5.
    """
    schedule, _instance = resolu
    debut_b = next(e.start_time for e in schedule.entries if e.job_id == "B")
    assert debut_b < CHARGE + 30, (
        f"B demarre a {debut_b} : il subit encore setup(JF,B) = 30"
    )


def test_les_deux_setups_respectent_lunique_technicien(resolu):
    """Reservation WR : JG->C et A->B ne peuvent pas tourner en parallele."""
    schedule, _instance = resolu
    fenetres = sorted(
        (e.setup.start_time, e.setup.end_time)
        for e in schedule.entries if e.setup and e.setup.duration > 0
    )
    assert fenetres == [(100, 120), (120, 125)], fenetres
