"""Le setup de contexte gauche occupe reellement la machine et un technicien WR.

DEFAUT DE VALIDITE, PREEXISTANT a la session du 2026-09-17. Le setup de contexte
gauche (dernier job fige -> premier job replanifie) etait pose comme une simple
inegalite arithmetique `s >= charge + duree`. Aucun intervalle ne le representait :
il n'entrait ni dans le `NoOverlap` de la machine, ni dans la `Cumulative` WR.

Pendant ce temps, `CPSATSolver` et `IncrementalOptimizer._setup_entry_for`
EMETTAIENT bien un `SetupEntry` pour ce setup — que le validateur canonique compte,
lui, dans les deux contraintes. L'occupation etait donc RAPPORTEE mais jamais
RESERVEE, et le solveur restait libre de superposer d'autres setups par-dessus.

Meme famille que les trois defauts latents reveles par le re-baselining de D12 et
que le cote gauche de H7 : toute emission de `SetupEntry` doit s'accompagner d'un
intervalle reserve dans le modele.

Le cas ci-dessous SATURE deliberement WR, ce qu'aucun scenario du depot ne faisait :
c'est la condition pour que le defaut se manifeste plutot que de rester latent.
"""
import pytest

from scheduling.models.context import BoundaryContext
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.solvers.cpsat_solver import CPSATSolver
from scheduling.validation import find_wr_violations, validate_schedule

DUREE_SETUP = 20


@pytest.fixture
def atelier_wr_sature():
    """Deux machines, UN SEUL technicien, un setup de contexte gauche sur chacune.

    Les deux setups sont dus a t=0 sur des machines differentes. Avec WR=1 ils ne
    peuvent pas tourner en parallele : l'un des deux doit attendre.
    """
    jobs = [
        Job(id="A", operations=[Operation("A", "M1", 10, 1)], deadline=30, weight=1.0),
        Job(id="B", operations=[Operation("B", "M2", 10, 1)], deadline=30, weight=1.0),
    ]
    setups = {
        ("JF", "A", "M1"): DUREE_SETUP,
        ("JG", "B", "M2"): DUREE_SETUP,
    }
    instance = ProblemInstance(
        jobs=jobs, machines=["M1", "M2"], setup_times=setups, wr=1,
    )
    contexte = BoundaryContext(
        last_job_per_machine={"M1": "JF", "M2": "JG"}, active_setups=[],
        pending_jobs=["JF", "JG"], machine_loads={"M1": 0, "M2": 0},
    )
    return instance, contexte


def _resous(instance, contexte):
    return CPSATSolver(
        timeout_seconds=10, num_search_workers=1, random_seed=42,
    ).solve_with_context(instance, contexte, None)


def test_les_setups_de_contexte_gauche_ne_depassent_pas_la_capacite_wr(
    atelier_wr_sature
):
    """C'est le test qui echoue sans la reservation : 2 setups pour 1 technicien."""
    instance, contexte = atelier_wr_sature
    schedule = _resous(instance, contexte)
    assert schedule is not None
    assert find_wr_violations(schedule, instance.wr) == []


def test_le_planning_reste_globalement_valide(atelier_wr_sature):
    instance, contexte = atelier_wr_sature
    schedule = _resous(instance, contexte)
    assert validate_schedule(schedule, instance=instance) == []


def test_les_deux_setups_sont_serialises_et_non_superposes(atelier_wr_sature):
    """Propriete observable : avec WR=1, les deux fenetres sont disjointes."""
    instance, contexte = atelier_wr_sature
    schedule = _resous(instance, contexte)
    fenetres = sorted(
        (e.setup.start_time, e.setup.end_time)
        for e in schedule.entries if e.setup and e.setup.duration > 0
    )
    assert len(fenetres) == 2, f"deux setups attendus, obtenu {fenetres}"
    (_d1, f1), (d2, _f2) = fenetres
    assert d2 >= f1, f"les deux setups se chevauchent : {fenetres}"


def test_les_dates_du_setup_gauche_sortent_du_modele(atelier_wr_sature):
    """Regle D8 : on n'emet jamais un SetupEntry dont les dates sont fabriquees.

    Avant correction, les dates etaient toujours `[charge, charge + duree]`,
    calculees apres coup. Ici la charge vaut 0 sur les deux machines : au moins
    un des deux setups DOIT donc etre decale, ce qu'un calcul apres coup ne
    pourrait pas produire.
    """
    instance, contexte = atelier_wr_sature
    schedule = _resous(instance, contexte)
    debuts = sorted(
        e.setup.start_time
        for e in schedule.entries if e.setup and e.setup.duration > 0
    )
    assert debuts[-1] > 0, (
        f"les deux setups partent de la charge machine (0) : {debuts}. "
        f"Les dates sont fabriquees, pas issues du modele."
    )


def test_le_setup_gauche_occupe_aussi_la_machine(atelier_wr_sature):
    """Le NoOverlap machine doit couvrir le setup, pas seulement l'operation."""
    instance, contexte = atelier_wr_sature
    schedule = _resous(instance, contexte)
    for entry in schedule.entries:
        if entry.setup and entry.setup.duration > 0:
            assert entry.setup.end_time <= entry.start_time, (
                f"{entry.job_id} : le setup {entry.setup.start_time}-"
                f"{entry.setup.end_time} deborde sur l'operation a {entry.start_time}"
            )
