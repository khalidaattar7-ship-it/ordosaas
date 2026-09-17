"""Le contexte gauche d'`InterWindowOptimizer` doit etre reellement transmis (H10).

`_optimize_junction` reoptimise un voisinage de jonction : `micro_jobs` ne contient que
les `junction_radius` derniers jobs de la fenetre gauche et les premiers de la droite.
Tout ce qui precede doit etre represente par un `BoundaryContext` gauche, et tout ce qui
suit par une borne droite. TROIS defauts distincts, tous dans la meme methode, faisaient
perdre ces representations :

  H10a — le filtrage des setups de la micro-instance utilisait un `and`, qui elimine
         exactement les paires (job precedent -> micro job) dont le contexte gauche a
         besoin. Un setup de 50 etait lu comme 0 : setup IMPAYE a la jonction.

  H10b — le garde `len(left.window.jobs) > junction_radius` laissait `left_context`
         entierement VIDE quand il etait faux. Avec les defauts du projet
         (min_jobs_per_window=5, junction_radius=10), toute fenetre de 5 a 10 jobs
         tombe dans ce cas EN PRODUCTION. Le micro-solveur replacait alors les jobs
         depuis t=0 en ignorant les fenetres anterieures : CHEVAUCHEMENT, et la
         jonction fautive etait ACCEPTEE parce qu'elle ameliore le TWT.

  H10c — `solve_with_context` accepte un `right_context` mais ne le lit JAMAIS : le mot
         n'apparait qu'a sa signature. Rien ne bornait donc la jonction a droite, et le
         micro-planning pouvait deborder sur les fenetres POSTERIEURES. Corrige ici par
         une garde conservatrice qui REJETTE la jonction debordante ; honorer
         `right_context` dans le solveur partage est l'amelioration structurelle
         correspondante, differee.

Ce module est aussi la premiere couverture directe de ce composant : il n'en avait
aucune, et c'est ce vide autant que la logique qui a laisse passer les trois defauts.
"""
import pytest

from scheduling.components.inter_window_optimizer import InterWindowOptimizer
from scheduling.models.context import BoundaryContext
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.schedule import Schedule, ScheduleEntry
from scheduling.models.window import Window, WindowResult
from scheduling.solvers.cpsat_solver import CPSATSolver
from scheduling.validation import validate_schedule
from tests.test_setups_payes import transitions_non_payees

SETUP_JONCTION = 50
DUREE = 10


def _op(job_id):
    return Operation(job_id, "M1", DUREE, 1)


def _entry(job_id, start):
    return ScheduleEntry(
        job_id=job_id, machine_id="M1", position_in_job=1,
        start_time=start, end_time=start + DUREE, duration=DUREE, setup=None,
    )


def _solveur():
    return CPSATSolver(timeout_seconds=10, num_search_workers=1, random_seed=42)


def _window_result(index, noms, jobs, debuts):
    schedule = Schedule(
        entries=[_entry(j, d) for j, d in zip(noms, debuts)], method_used="cpsat",
    )
    return WindowResult(
        window=Window(index=index, t_start=min(debuts), t_end=max(debuts) + DUREE,
                      jobs=[jobs[j] for j in noms]),
        schedule=schedule, exit_context=BoundaryContext.empty(),
        objective=0.0, method="cpsat",
    )


# ==========================================================================
# H10a — le setup de jonction doit etre PAYE
# ==========================================================================
@pytest.fixture
def jonction_avec_setup():
    """Fenetre gauche L1..L4, droite R1,R2, rayon 2.

    Le contexte gauche est donc {L1, L2}, et L2 est le dernier job fige sur M1.
    Le setup L2 -> (n'importe quel micro job) vaut 50 : il est du QUEL QUE SOIT le
    job que le solveur place en premier, ce qui rend le defaut inevitable plutot
    que dependant d'un choix de CP-SAT.
    """
    noms_g, noms_d = ["L1", "L2", "L3", "L4"], ["R1", "R2"]
    jobs = {
        j: Job(id=j, operations=[_op(j)], deadline=200, weight=1.0)
        for j in noms_g + noms_d
    }
    setups = {("L2", cible, "M1"): SETUP_JONCTION
              for cible in ("L3", "L4", "R1", "R2")}
    setups.update({
        ("L3", "L4", "M1"): 2, ("L4", "R1", "M1"): 2, ("R1", "R2", "M1"): 2,
        ("L4", "L3", "M1"): 30, ("R1", "L3", "M1"): 30,
    })
    instance = ProblemInstance(
        jobs=list(jobs.values()), machines=["M1"], setup_times=setups, wr=2,
    )
    gauche = _window_result(0, noms_g, jobs, [0, 10, 20, 30])
    droite = _window_result(1, noms_d, jobs, [100, 110])
    return instance, gauche, droite


def test_le_setup_du_contexte_gauche_est_paye_a_la_jonction(jonction_avec_setup):
    """C'est le test qui echoue avec le filtrage `and` : ecart de 0 pour 50 dus."""
    instance, gauche, droite = jonction_avec_setup
    optim = InterWindowOptimizer(cpsat_solver=_solveur(), junction_radius=2)
    resultat = optim._optimize_junction(
        {"index": 0, "cost": 1.0, "left": gauche, "right": droite},
        [gauche, droite], instance,
    )
    assert resultat, "la jonction n'a produit aucun resultat"

    micro = resultat[0]["micro_schedule"]
    fin_contexte_gauche = 20  # L2 occupe [10,20]
    premier = min(micro.entries, key=lambda e: e.start_time)
    du = instance.get_setup("L2", premier.job_id, "M1")
    ecart = premier.start_time - fin_contexte_gauche
    assert ecart >= du, (
        f"{premier.job_id} demarre a {premier.start_time}, soit {ecart} apres L2, "
        f"alors que le setup L2->{premier.job_id} vaut {du}"
    )


def test_la_micro_instance_voit_le_setup_du_contexte_gauche(jonction_avec_setup):
    """Propriete de construction : le filtrage ne doit pas eliminer ces paires."""
    instance, gauche, droite = jonction_avec_setup
    optim = InterWindowOptimizer(cpsat_solver=_solveur(), junction_radius=2)
    micro_ids = {
        j.id for j in gauche.window.jobs[-2:] + droite.window.jobs[:2]
    }
    filtre = {
        k: v for k, v in instance.setup_times.items()
        if k[0] in micro_ids or k[1] in micro_ids
    }
    assert filtre.get(("L2", "L3", "M1")) == SETUP_JONCTION, (
        "le filtrage elimine la paire dont le contexte gauche a besoin"
    )


def test_le_setup_de_jonction_est_remonte_avec_des_dates_du_modele(
    jonction_avec_setup
):
    """Regle D8 : jamais de SetupEntry dont les dates sont fabriquees."""
    instance, gauche, droite = jonction_avec_setup
    optim = InterWindowOptimizer(cpsat_solver=_solveur(), junction_radius=2)
    resultat = optim._optimize_junction(
        {"index": 0, "cost": 1.0, "left": gauche, "right": droite},
        [gauche, droite], instance,
    )
    micro = resultat[0]["micro_schedule"]
    premier = min(micro.entries, key=lambda e: e.start_time)
    assert premier.setup is not None, (
        f"{premier.job_id} ne porte aucun SetupEntry alors qu'un setup lui est du"
    )
    assert premier.setup.from_job_id == "L2"
    assert premier.setup.duration == SETUP_JONCTION
    assert premier.setup.end_time <= premier.start_time


# ==========================================================================
# H10b — une fenetre gauche plus petite que le rayon ne doit pas vider le contexte
# ==========================================================================
@pytest.fixture
def trois_fenetres():
    """W0 [0,20], W1 [20,40], W2 [40,60] sur M1, deux jobs chacune.

    Avec junction_radius=10 — la valeur par DEFAUT du projet — la fenetre gauche de
    la jonction W1/W2 compte 2 jobs, donc moins que le rayon.
    """
    groupes = [["A1", "A2"], ["B1", "B2"], ["C1", "C2"]]
    jobs = {
        j: Job(id=j, operations=[_op(j)], deadline=200, weight=1.0)
        for g in groupes for j in g
    }
    instance = ProblemInstance(
        jobs=list(jobs.values()), machines=["M1"], setup_times={}, wr=2,
    )
    fenetres = [
        _window_result(i, g, jobs, [20 * i, 20 * i + DUREE])
        for i, g in enumerate(groupes)
    ]
    return instance, fenetres


def test_la_jonction_ne_recouvre_pas_les_fenetres_anterieures(trois_fenetres):
    """C'est le test qui echoue sans H10b : C1 et C2 replaces par-dessus W0."""
    instance, fenetres = trois_fenetres
    optim = InterWindowOptimizer(cpsat_solver=_solveur(), junction_radius=10)
    assert len(fenetres[1].window.jobs) <= optim.junction_radius, (
        "le cas de test suppose une fenetre gauche plus petite que le rayon"
    )

    resultat = optim._optimize_junction(
        {"index": 1, "cost": 1.0, "left": fenetres[1], "right": fenetres[2]},
        fenetres, instance,
    )
    assert resultat, "la jonction n'a produit aucun resultat"

    final = optim._assemble_schedule(
        optim._build_applied(fenetres, resultat), instance
    )
    assert validate_schedule(final, instance=instance) == []


def test_la_jonction_demarre_apres_la_charge_des_fenetres_anterieures(trois_fenetres):
    """Propriete observable : rien ne repart avant la fin de W0."""
    instance, fenetres = trois_fenetres
    optim = InterWindowOptimizer(cpsat_solver=_solveur(), junction_radius=10)
    resultat = optim._optimize_junction(
        {"index": 1, "cost": 1.0, "left": fenetres[1], "right": fenetres[2]},
        fenetres, instance,
    )
    micro = resultat[0]["micro_schedule"]
    fin_w0 = max(e.end_time for e in fenetres[0].schedule.entries)
    premier = min(e.start_time for e in micro.entries)
    assert premier >= fin_w0, (
        f"la jonction redemarre a {premier}, avant la fin de W0 ({fin_w0})"
    )


def test_aucune_transition_impayee_dans_le_planning_reassemble(trois_fenetres):
    instance, fenetres = trois_fenetres
    optim = InterWindowOptimizer(cpsat_solver=_solveur(), junction_radius=10)
    resultat = optim._optimize_junction(
        {"index": 1, "cost": 1.0, "left": fenetres[1], "right": fenetres[2]},
        fenetres, instance,
    )
    final = optim._assemble_schedule(
        optim._build_applied(fenetres, resultat), instance
    )
    assert transitions_non_payees(final, instance) == []


# ==========================================================================
# H10c — la jonction ne doit pas deborder sur les fenetres POSTERIEURES
# ==========================================================================
@pytest.fixture
def trois_fenetres_setups_lourds():
    """W0, W1, W2 sur M1. Setups lourds entre les micro jobs de la jonction W0/W1.

    Le voisinage reoptimise ne tient alors plus dans l'espace [0,40] qu'il occupait,
    et deborde sur W2 [40,60] — que rien ne protege, `solve_with_context` ignorant
    totalement son parametre `right_context`.
    """
    groupes = [["A1", "A2"], ["B1", "B2"], ["C1", "C2"]]
    jobs = {
        j: Job(id=j, operations=[_op(j)], deadline=200, weight=1.0)
        for g in groupes for j in g
    }
    micro = ["A1", "A2", "B1", "B2"]
    setups = {
        (a, b, "M1"): 15 for a in micro for b in micro if a != b
    }
    instance = ProblemInstance(
        jobs=list(jobs.values()), machines=["M1"], setup_times=setups, wr=2,
    )
    fenetres = [
        _window_result(i, g, jobs, [20 * i, 20 * i + DUREE])
        for i, g in enumerate(groupes)
    ]
    return instance, fenetres


def test_une_jonction_qui_deborde_sur_la_suite_est_rejetee(
    trois_fenetres_setups_lourds
):
    """Garde conservatrice : mieux vaut perdre la jonction qu'un planning valide."""
    instance, fenetres = trois_fenetres_setups_lourds
    optim = InterWindowOptimizer(cpsat_solver=_solveur(), junction_radius=10)
    resultat = optim._optimize_junction(
        {"index": 0, "cost": 1.0, "left": fenetres[0], "right": fenetres[1]},
        fenetres, instance,
    )
    assert resultat == [], (
        "la jonction deborde sur W2 et aurait du etre rejetee"
    )


def test_le_planning_reste_valide_quand_la_jonction_deborde(
    trois_fenetres_setups_lourds
):
    """Sans la garde, le reassemblage produit des chevauchements sur M1."""
    instance, fenetres = trois_fenetres_setups_lourds
    optim = InterWindowOptimizer(cpsat_solver=_solveur(), junction_radius=10)
    resultat = optim._optimize_junction(
        {"index": 0, "cost": 1.0, "left": fenetres[0], "right": fenetres[1]},
        fenetres, instance,
    )
    final = optim._assemble_schedule(
        optim._build_applied(fenetres, resultat), instance
    )
    assert validate_schedule(final, instance=instance) == []


def test_une_jonction_qui_ne_deborde_pas_reste_acceptee(trois_fenetres):
    """La garde ne doit pas rejeter les jonctions legitimes."""
    instance, fenetres = trois_fenetres
    optim = InterWindowOptimizer(cpsat_solver=_solveur(), junction_radius=10)
    resultat = optim._optimize_junction(
        {"index": 1, "cost": 1.0, "left": fenetres[1], "right": fenetres[2]},
        fenetres, instance,
    )
    assert resultat, "une jonction qui ne deborde pas a ete rejetee a tort"
