"""
Les temps de setup sont-ils reellement payes ? (H8 / H9)

Ce module verrouille la correction du defaut decouvert par le livrable 3 de la
Discussion 2 : les booleens gouvernant les intervalles de setup n'etaient jamais
forces, si bien que CP-SAT ne payait aucun setup.

Les tests portent sur la propriete OBSERVABLE — entre deux operations consecutives
sur une machine, l'ecart doit couvrir le setup du au titre de cette transition — et
non sur la technique employee pour l'obtenir. Ils resteraient valides si la
modelisation changeait a nouveau.

Le validateur canonique (`scheduling/validation.py`) ne verifie PAS cette propriete :
il ne controle que chevauchement, precedence et Cumulative WR. C'est ce qui avait
laisse le defaut passer inapercu pendant tout le projet.
"""
import pytest

from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.solvers.cpsat_solver import CPSATSolver, _borne_horizon


def transitions_non_payees(schedule, instance) -> list:
    """Transitions consecutives dont l'ecart ne couvre pas le setup du.

    C'est la verification qui aurait detecte H8/H9 des leur introduction.
    """
    manques = []
    par_machine = {}
    for entry in schedule.entries:
        par_machine.setdefault(entry.machine_id, []).append(entry)

    for machine_id, entrees in par_machine.items():
        entrees.sort(key=lambda e: e.start_time)
        for precedente, suivante in zip(entrees, entrees[1:]):
            requis = instance.get_setup(precedente.job_id, suivante.job_id, machine_id)
            ecart = suivante.start_time - precedente.end_time
            if ecart < requis:
                manques.append(
                    f"{machine_id} : {precedente.job_id}->{suivante.job_id} "
                    f"exige {requis}, ecart de {ecart}"
                )
    return manques


def setup_theorique(schedule, instance) -> int:
    """Somme des setups dus au titre des sequences reellement produites."""
    total = 0
    par_machine = {}
    for entry in schedule.entries:
        par_machine.setdefault(entry.machine_id, []).append(entry)
    for machine_id, entrees in par_machine.items():
        entrees.sort(key=lambda e: e.start_time)
        for precedente, suivante in zip(entrees, entrees[1:]):
            total += instance.get_setup(precedente.job_id, suivante.job_id, machine_id)
    return total


# ==========================================================================
# H8 — le solveur initial
# ==========================================================================
@pytest.fixture
def atelier_jouet():
    """3 jobs, 1 machine, tous les setups a 7 : le resultat est calculable a la main.

    Quel que soit l'ordre choisi, la sequence comporte deux transitions, donc
    exactement 14 unites de setup, et le makespan vaut 3*10 + 2*7 = 44.
    """
    jobs = [
        Job(id=f"J{i}", operations=[Operation(f"J{i}", "M1", 10, 1)],
            deadline=1000, weight=1.0)
        for i in (1, 2, 3)
    ]
    setups = {
        (a, b, "M1"): 7
        for a in ("J1", "J2", "J3") for b in ("J1", "J2", "J3") if a != b
    }
    return ProblemInstance(jobs=jobs, machines=["M1"], setup_times=setups, wr=1)


def test_cas_jouet_le_makespan_inclut_exactement_les_setups(atelier_jouet):
    """Verification exacte : le setup n'est ni oublie, ni compte deux fois."""
    schedule = CPSATSolver(timeout_seconds=10).solve(atelier_jouet)

    assert schedule is not None
    assert schedule.horizon == 44, (
        f"makespan {schedule.horizon}, attendu 3*10 + 2*7 = 44"
    )
    assert schedule.total_setup_time == 14
    assert transitions_non_payees(schedule, atelier_jouet) == []


def test_cas_jouet_chaque_transition_porte_son_setup(atelier_jouet):
    """Chaque transition emet un SetupEntry, aux dates du modele."""
    schedule = CPSATSolver(timeout_seconds=10).solve(atelier_jouet)
    entrees = sorted(schedule.entries, key=lambda e: e.start_time)

    assert entrees[0].setup is None, "la premiere operation n'a pas de predecesseur"
    for precedente, suivante in zip(entrees, entrees[1:]):
        assert suivante.setup is not None
        assert suivante.setup.from_job_id == precedente.job_id
        assert suivante.setup.duration == 7
        assert suivante.setup.start_time >= precedente.end_time
        assert suivante.setup.end_time <= suivante.start_time


def test_sur_instance_reelle_tout_setup_du_est_paye(example_instance):
    """Critere d'acceptation de la correction de H8, sur les 10 jobs reels.

    Assertion EXPLICITE, et non simple absence d'erreur : pour tout couple de jobs
    consecutifs sur une meme machine, debut(suivant) >= fin(precedent) + setup_du.

    Avant correction, cette instance presentait 18 transitions en violation et
    352 unites de setup dues pour 0 payee.
    """
    schedule = CPSATSolver(timeout_seconds=30).solve(example_instance)

    assert schedule is not None
    manques = transitions_non_payees(schedule, example_instance)
    assert manques == [], (
        f"{len(manques)} transition(s) sans setup paye :\n  - " + "\n  - ".join(manques)
    )


def test_sur_instance_reelle_le_temps_de_setup_est_strictement_positif(example_instance):
    """Test canari : un total nul signifierait que le defaut est revenu.

    C'est le symptome le plus direct de H8 — `total_setup_time` valait exactement 0
    alors que l'instance declare 247 paires de setups non nuls.
    """
    schedule = CPSATSolver(timeout_seconds=30).solve(example_instance)

    assert schedule.total_setup_time > 0, (
        "aucun setup paye : le defaut H8 est revenu"
    )
    assert schedule.total_setup_time == setup_theorique(schedule, example_instance), (
        "le temps de setup emis ne correspond pas aux transitions reellement produites"
    )


# ==========================================================================
# Borne d'horizon resserree (partie integrante de la correction)
# ==========================================================================
def test_la_borne_dhorizon_est_resserree_et_reste_un_majorant(example_instance):
    """La borne doit etre plus fine que l'ancienne, sans cesser d'etre valide.

    L'ancien calcul (`ProblemInstance.horizon`) majorait les setups par la somme de
    TOUTES les paires declarees — un artefact du defaut H8, sans incidence tant
    qu'aucun setup n'etait paye.
    """
    resserree = _borne_horizon(example_instance)

    assert resserree < example_instance.horizon, "la borne devrait etre plus fine"

    schedule = CPSATSolver(timeout_seconds=30).solve(example_instance)
    assert schedule.horizon <= resserree, (
        f"makespan {schedule.horizon} au-dela de la borne {resserree} : "
        f"ce n'est plus un majorant"
    )


def test_la_borne_dhorizon_majore_meme_un_cas_degenere():
    """Cas limite : une seule machine, tous les setups au maximum.

    Le pire cas theorique est une execution entierement sequentielle sur une machine,
    chaque operation precedee de son plus long setup entrant possible.
    """
    jobs = [
        Job(id=f"J{i}", operations=[Operation(f"J{i}", "M1", 10, 1)],
            deadline=10_000, weight=1.0)
        for i in range(5)
    ]
    setups = {
        (a.id, b.id, "M1"): 25 for a in jobs for b in jobs if a.id != b.id
    }
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times=setups, wr=1)

    # 5 operations de 10, 4 transitions de 25 : makespan reel = 50 + 100 = 150.
    schedule = CPSATSolver(timeout_seconds=10).solve(instance)
    assert schedule.horizon == 150
    assert schedule.horizon <= _borne_horizon(instance)
    assert transitions_non_payees(schedule, instance) == []
