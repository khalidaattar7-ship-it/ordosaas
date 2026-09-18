"""Le planning final du LNS est-il valide ? (decouvert le 2026-09-18)

Personne ne l'avait jamais verifie. `test_lns.py` exerce pourtant les quatre phases de
bout en bout, mais n'assertit que le nombre d'entrees, un TWT positif et la presence des
KPI — jamais la VALIDITE du planning produit. C'est ce trou qui a laisse passer H10b et
H10c, et c'est lui qui expose ici un defaut distinct.

LE DEFAUT : la capacite WR n'est jamais contrainte ENTRE fenetres.

  `ContextPropagator.build_left_context` renvoie `active_setups=[]` INCONDITIONNELLEMENT
  (context_propagator.py:47). Or `CPSATSolver.solve_with_context:306` consomme bien ce
  champ pour alimenter la Cumulative WR — la tuyauterie existe — et
  `IncrementalContextBuilder:79` le remplit reellement, son docstring precisant meme
  « Ajout par rapport au LNS ». L'architecture incrementale a identifie et comble ce
  manque ; le LNS ne l'a jamais fait.

Consequence : chaque fenetre respecte WR en interne, mais deux setups de fenetres
voisines peuvent se chevaucher sans que rien ne s'y oppose.

ISOLATION, mesuree avant d'accuser quoi que ce soit :

    chaque fenetre isolement   0 violation
    assemble apres Phase 3     1 violation
    apres Phase 4              1 violation, au MEME instant

`InterWindowOptimizer` n'en est donc ni la cause ni le remede.

CORRIGE le 2026-09-18 : `build_left_context` transmet desormais les setups de la fenetre
precedente pouvant encore consommer un technicien. Les marqueurs `xfail(strict=True)` qui
exposaient le defaut ont ete retires des que la correction les a fait passer — c'est leur
`strict=True` qui l'a signale, un xpass etant traite comme un echec.

Ces tests restent en place comme GARDE-FOU permanent : ils echoueront si la contrainte WR
inter-fenetres redevient inoperante.
"""
import pytest

from scheduling.solvers.lns_recursive import LNSRecursiveSolver
from scheduling.validation import find_wr_violations, validate_schedule
from tests.benchmarks.avgerinos import generate_avgerinos_instance

# Instance multi-fenetres : 55 jobs pour 20 par fenetre, donc 3 fenetres.
NB_JOBS = 55
SEED = 9


@pytest.fixture(scope="module")
def resolution_lns():
    instance = generate_avgerinos_instance(nb_machines=2, nb_jobs=NB_JOBS, seed=SEED)
    schedule = LNSRecursiveSolver(
        cpsat_timeout=3, max_jobs_per_window=20,
    ).solve(instance)
    return schedule, instance


def test_le_lns_planifie_bien_toutes_les_operations(resolution_lns):
    """Garde-fou de base : rien ne doit disparaitre a l'assemblage."""
    schedule, instance = resolution_lns
    attendu = sum(len(j.operations) for j in instance.jobs)
    assert len(schedule.entries) == attendu


def test_le_planning_final_du_lns_respecte_la_capacite_wr(resolution_lns):
    """LE test qui a expose le defaut, devenu garde-fou permanent.

    Avant correction : 1 violation sur 20 executions sur 20, tous budgets confondus.
    Apres : 0 sur 22.
    """
    schedule, instance = resolution_lns
    assert find_wr_violations(schedule, instance.wr) == []


def test_le_planning_final_du_lns_est_globalement_valide(resolution_lns):
    """Le validateur canonique du projet doit accepter ce que le LNS produit."""
    schedule, instance = resolution_lns
    assert validate_schedule(schedule, instance=instance) == []


def test_chaque_fenetre_respecte_wr_isolement(resolution_lns):
    """La contrainte EST appliquee dans chaque fenetre — le defaut est aux frontieres.

    Ce test delimite le defaut : il n'y a rien a corriger dans la resolution d'une
    fenetre, seulement dans ce qui est transmis d'une fenetre a la suivante.
    """
    from scheduling.models.context import BoundaryContext

    _schedule, instance = resolution_lns
    solveur = LNSRecursiveSolver(cpsat_timeout=3, max_jobs_per_window=20)
    atcs = solveur.atcs_solver.solve(instance)
    fenetres = solveur.window_manager.create_windows(instance, atcs)
    assert len(fenetres) > 1, "le cas de test suppose plusieurs fenetres"

    gauche = BoundaryContext.empty()
    for i, fenetre in enumerate(fenetres):
        droite = (
            solveur.context_propagator.build_right_context(fenetres[i + 1], atcs, instance)
            if i + 1 < len(fenetres) else None
        )
        resultat = solveur._optimize_window_recursive(
            window=fenetre, instance=solveur._create_window_instance(fenetre, instance),
            full_instance=instance, left_context=gauche, right_context=droite,
            atcs_schedule=atcs, depth=0,
        )
        assert find_wr_violations(resultat.schedule, instance.wr) == [], (
            f"fenetre {i} : la contrainte devrait etre respectee A L'INTERIEUR"
        )
        gauche = solveur.context_propagator.build_left_context(resultat, instance)


def test_le_contexte_gauche_du_lns_transmet_les_setups_actifs(resolution_lns):
    """La CAUSE, verrouillee comme propriete observable — pas seulement le symptome.

    Ce test etait ecrit a l'envers lors de la decouverte (il affirmait que la liste
    etait vide) ; il est inverse ici, en meme temps que le correctif.
    """
    from scheduling.models.context import BoundaryContext

    _schedule, instance = resolution_lns
    solveur = LNSRecursiveSolver(cpsat_timeout=3, max_jobs_per_window=20)
    atcs = solveur.atcs_solver.solve(instance)
    fenetres = solveur.window_manager.create_windows(instance, atcs)
    resultat = solveur._optimize_window_recursive(
        window=fenetres[0],
        instance=solveur._create_window_instance(fenetres[0], instance),
        full_instance=instance, left_context=BoundaryContext.empty(),
        right_context=None, atcs_schedule=atcs, depth=0,
    )
    contexte = solveur.context_propagator.build_left_context(resultat, instance)
    assert contexte.active_setups, (
        "le contexte gauche ne transmet aucun setup actif : la Cumulative WR "
        "redevient inoperante entre fenetres"
    )
    # Format attendu par `CPSATSolver.solve_with_context` pour la Cumulative.
    for machine_id, from_job, to_job, debut, fin in contexte.active_setups:
        assert fin > debut, f"setup de duree nulle transmis : {machine_id} {from_job}->{to_job}"
        assert fin > min(contexte.machine_loads.values()), (
            "un setup s'achevant avant la frontiere ne peut rien chevaucher : "
            "il n'a pas a etre transmis"
        )
