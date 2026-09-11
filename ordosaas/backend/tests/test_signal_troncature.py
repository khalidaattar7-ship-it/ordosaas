"""
Signal de troncature : la cascade a-t-elle ete coupee en pleine propagation ?

Corrige le defaut d'articulation entre D7 (bornes de recherche, 0.15 / 0.20) et H5
(seuil de repli, 0.50) : 20 % < 50 %, donc le plafond coupait toujours la zone avant
que le seuil puisse la voir. Voir D13 dans docs/CONTEXTE_ET_DECISIONS.md.

`ImpactZone` porte desormais DEUX drapeaux, a ne pas confondre :

- `truncated` — une borne a coupe quelque chose, quelle qu'en soit la raison ;
- `truncated_before_convergence` — la coupe est intervenue alors qu'un retard
  residuel progressait encore, sans que rien ne l'ait absorbe.

Seul le second recommande le repli. Les tests ci-dessous couvrent les DEUX mecanismes
de cascade (contention et precedence) et les deux sens (signal vrai / signal faux).
"""
import pytest

from scheduling.components.impact_analyzer import ImpactAnalyzer
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.perturbation import make_event
from scheduling.models.schedule import Schedule, ScheduleEntry


def _entry(job_id, machine_id, position, start, duration):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine_id, position_in_job=position,
        start_time=start, end_time=start + duration, duration=duration,
    )


def _instance(jobs, machines):
    return ProblemInstance(jobs=jobs, machines=machines, setup_times={}, wr=1)


# ==========================================================================
# CONTENTION — le mecanisme qui porte la croissance a grande echelle
# ==========================================================================
@pytest.fixture
def machine_saturee():
    """M1 sans le moindre temps mort : J1..J6 bout a bout, de 100 a 400.

    Aucun trou ne peut absorber quoi que ce soit : un retard injecte au debut se
    propage mecaniquement jusqu'au bout de la machine.
    """
    entries = [_entry(f"J{i}", "M1", 1, 100 + 50 * i, 50) for i in range(6)]
    jobs = [
        Job(id=f"J{i}", operations=[Operation(f"J{i}", "M1", 50, 1)],
            deadline=2000, weight=1.0)
        for i in range(6)
    ]
    return Schedule(entries=entries), _instance(jobs, ["M1"])


def test_contention_coupee_en_pleine_propagation(machine_saturee):
    """Cascade coupee par l'horizon alors que le retard progresse encore.

    L'horizon s'arrete a 250 alors que la machine est occupee jusqu'a 400 sans le
    moindre trou : au point de coupe, le retard est intact et n'a nulle part ou etre
    absorbe. C'est exactement le cas que D7 rendait invisible.
    """
    schedule, instance = machine_saturee
    event = make_event("machine_breakdown", timestamp=50, machine_id="M1",
                       start_time=100, end_time=180)
    zone = ImpactAnalyzer(search_horizon=200, max_impacted_jobs=50).analyze(
        event, schedule, instance
    )

    assert zone.truncated is True
    assert zone.truncated_before_convergence is True


def test_contention_convergee_naturellement_ne_signale_rien():
    """Le retard est absorbe par un trou, bien avant la borne : aucun signal.

    M1 : J0[100-150], puis un trou de 300 unites, puis J1[450-500]. Une panne de
    20 unites est integralement absorbee par le trou. L'horizon (2000) est tres
    au-dela : rien n'est coupe.
    """
    entries = [_entry("J0", "M1", 1, 100, 50), _entry("J1", "M1", 1, 450, 50)]
    jobs = [
        Job(id=f"J{i}", operations=[Operation(f"J{i}", "M1", 50, 1)],
            deadline=2000, weight=1.0)
        for i in range(2)
    ]
    event = make_event("machine_breakdown", timestamp=50, machine_id="M1",
                       start_time=100, end_time=120)
    zone = ImpactAnalyzer(search_horizon=2000, max_impacted_jobs=50).analyze(
        event, Schedule(entries=entries), _instance(jobs, ["M1"])
    )

    assert zone.truncated is False
    assert zone.truncated_before_convergence is False
    assert zone.fallback_recommended is False


def test_contention_coupee_sur_une_convergence_acquise_ne_signale_pas():
    """Coupe d'horizon tombant sur un trou qui aurait absorbe le residuel.

    La borne coupe bien la recherche (`truncated` vrai), mais le trou precedant
    l'entree hors horizon suffit a eteindre le retard : la cascade aurait converge
    la. Sans ce discernement, cette coupe compterait a tort comme une troncature.

    M1 : J0[100-150] puis J1[500-550]. Panne de 10 unites. L'horizon s'arrete a 200,
    donc J1 est hors champ — mais le trou de 350 unites qui la precede aurait
    absorbe les 10 unites de retard bien avant.
    """
    entries = [_entry("J0", "M1", 1, 100, 50), _entry("J1", "M1", 1, 500, 50)]
    jobs = [
        Job(id=f"J{i}", operations=[Operation(f"J{i}", "M1", 50, 1)],
            deadline=2000, weight=1.0)
        for i in range(2)
    ]
    event = make_event("machine_breakdown", timestamp=50, machine_id="M1",
                       start_time=100, end_time=110)
    zone = ImpactAnalyzer(search_horizon=150, max_impacted_jobs=50).analyze(
        event, Schedule(entries=entries), _instance(jobs, ["M1"])
    )

    assert zone.truncated is True, "la borne coupe bien la recherche"
    assert zone.truncated_before_convergence is False, (
        "le trou aurait absorbe le residuel : ce n'est pas une coupe active"
    )


def test_le_plafond_de_jobs_est_une_coupe_active(machine_saturee):
    """Le plafond refuse un job que la cascade reclamait.

    L'horizon est large, seul le nombre de jobs borne la zone. Un plafond atteint
    signifie par construction que la propagation voulait aller plus loin.
    """
    schedule, instance = machine_saturee
    event = make_event("machine_breakdown", timestamp=50, machine_id="M1",
                       start_time=100, end_time=180)
    zone = ImpactAnalyzer(search_horizon=10_000, max_impacted_jobs=2).analyze(
        event, schedule, instance
    )

    assert zone.nb_impacted_jobs == 2
    assert zone.truncated is True
    assert zone.truncated_before_convergence is True


# ==========================================================================
# PRECEDENCE — exclue du signal, DELIBEREMENT (cf. D13)
# ==========================================================================
@pytest.fixture
def job_en_trois_operations():
    """Un job dont les trois operations s'etalent loin : J1 sur M1, M2, M3.

    M1[100-150], M2[600-650], M3[1100-1150]. Les deux dernieres sont tres au-dela
    d'un horizon court.

    Deux jobs temoins (J2, J3) occupent une machine M4 que rien ne perturbe. Leur
    seul role est de porter le nombre de jobs futurs a trois, pour que J1 seul
    represente 33 % et reste SOUS le seuil de repli : le test isole ainsi le signal
    de troncature de la regle de ratio preexistante, qui declencherait sinon a elle
    seule.
    """
    entries = [
        _entry("J1", "M1", 1, 100, 50),
        _entry("J1", "M2", 2, 600, 50),
        _entry("J1", "M3", 3, 1100, 50),
        _entry("J2", "M4", 1, 100, 50),
        _entry("J3", "M4", 1, 160, 50),
    ]
    jobs = [
        Job(id="J1",
            operations=[Operation("J1", "M1", 50, 1), Operation("J1", "M2", 50, 2),
                        Operation("J1", "M3", 50, 3)],
            deadline=2000, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M4", 50, 1)],
            deadline=2000, weight=1.0),
        Job(id="J3", operations=[Operation("J3", "M4", 50, 1)],
            deadline=2000, weight=1.0),
    ]
    return Schedule(entries=entries), _instance(jobs, ["M1", "M2", "M3", "M4"])


def test_precedence_coupee_signale_la_troncature_mais_pas_le_repli(
    job_en_trois_operations
):
    """Exclusion assumee : une coupe de precedence ne recommande pas le repli.

    La cascade de precedence propage le retard SANS jamais l'absorber. Qu'un
    successeur lointain tombe hors horizon decoule de ce conservatisme, pas d'une
    cascade reellement large — et elle est de toute facon bornee aux operations
    restantes d'un seul job. L'inclure ferait declencher le repli presque partout,
    reproduisant a l'envers le sur-declenchement que D7 avait corrige.

    Ce test FIGE ce choix : le jour ou l'absorption sera modelisee sur la
    precedence (amelioration differee, cf. D13), il faudra mettre a jour la
    decision plutot que contourner le test.
    """
    schedule, instance = job_en_trois_operations
    event = make_event("duration_change", timestamp=50, job_id="J1",
                       position_in_job=1, machine_id="M1", new_duration=90)
    zone = ImpactAnalyzer(search_horizon=200, max_impacted_jobs=50).analyze(
        event, schedule, instance
    )

    assert zone.truncated is True, "les operations 2 et 3 sont hors horizon"
    assert zone.truncated_before_convergence is False
    # Un seul job touche sur trois futurs : la regle de ratio ne se declenche pas
    # non plus, donc l'absence de repli vient bien de l'exclusion de la precedence.
    assert zone.ratio_future_jobs_affected < 0.5
    assert zone.fallback_recommended is False


def test_precedence_entierement_dans_lhorizon_ne_signale_rien(
    job_en_trois_operations
):
    """Contre-epreuve : avec un horizon large, plus aucune coupe."""
    schedule, instance = job_en_trois_operations
    event = make_event("duration_change", timestamp=50, job_id="J1",
                       position_in_job=1, machine_id="M1", new_duration=90)
    zone = ImpactAnalyzer(search_horizon=10_000, max_impacted_jobs=50).analyze(
        event, schedule, instance
    )

    assert zone.truncated is False
    assert zone.truncated_before_convergence is False


# ==========================================================================
# Le drapeau par defaut
# ==========================================================================
def test_le_signal_est_faux_par_defaut():
    """Une zone sans aucune perturbation ne signale rien."""
    entries = [_entry("J0", "M1", 1, 100, 50)]
    jobs = [Job(id="J0", operations=[Operation("J0", "M1", 50, 1)],
                deadline=2000, weight=1.0)]
    event = make_event("machine_breakdown", timestamp=50, machine_id="M9",
                       start_time=100, end_time=120)
    zone = ImpactAnalyzer(search_horizon=10_000, max_impacted_jobs=50).analyze(
        event, Schedule(entries=entries), _instance(jobs, ["M1"])
    )

    assert zone.nb_impacted_jobs == 0
    assert zone.truncated_before_convergence is False
    assert zone.fallback_recommended is False
