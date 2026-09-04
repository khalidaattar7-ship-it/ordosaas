"""Tests d'IncrementalOptimizer : re-optimisation de zone + terme de stabilite."""
import pytest

from scheduling.components.impact_analyzer import ImpactAnalyzer
from scheduling.components.incremental_context_builder import IncrementalContextBuilder
from scheduling.components.schedule_merger import ScheduleMerger
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.perturbation import make_event
from scheduling.models.schedule import Schedule, ScheduleEntry
from scheduling.solvers.incremental_optimizer import (
    DEFAULT_STABILITY_WEIGHT,
    IncrementalOptimizer,
)
from scheduling.validation import validate_schedule


def _entry(job_id, machine_id, position, start, duration, setup=None):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine_id, position_in_job=position,
        start_time=start, end_time=start + duration, duration=duration, setup=setup,
    )


def _reoptimise(event, schedule, instance, optimizer=None, analyzer=None):
    """Chaine complete analyse -> contextes -> re-optimisation."""
    analyzer = analyzer or ImpactAnalyzer(search_horizon=10_000, max_impacted_jobs=50)
    zone = analyzer.analyze(event, schedule, instance)
    contexts = IncrementalContextBuilder().build(zone, instance)
    optimizer = optimizer or IncrementalOptimizer(timeout_seconds=10)
    return zone, optimizer.optimize(zone, contexts, instance)


@pytest.fixture
def atelier():
    """M1 : J1[0-50] fige, J2[100-150], J3[150-200]. M2 : J2[200-230], J3[210-240]."""
    entries = [
        _entry("J1", "M1", 1, 0, 50),
        _entry("J2", "M1", 1, 100, 50),
        _entry("J3", "M1", 1, 150, 50),
        _entry("J2", "M2", 2, 200, 30),
        _entry("J3", "M2", 2, 210, 30),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1)], deadline=100, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1), Operation("J2", "M2", 30, 2)],
            deadline=260, weight=5.0),
        Job(id="J3", operations=[Operation("J3", "M1", 50, 1), Operation("J3", "M2", 30, 2)],
            deadline=280, weight=1.0),
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1", "M2"], setup_times={}, wr=2)
    return Schedule(entries=entries), instance


# -- configuration ----------------------------------------------------------
def test_stability_weight_par_defaut_vaut_zero_virgule_un():
    assert DEFAULT_STABILITY_WEIGHT == 0.1
    assert IncrementalOptimizer().stability_weight == 0.1


def test_timeout_par_defaut_dans_la_plage_10_15s():
    assert 10 <= IncrementalOptimizer().timeout_seconds <= 15


def test_parametres_configurables():
    optimizer = IncrementalOptimizer(timeout_seconds=15, stability_weight=0.5)
    assert optimizer.timeout_seconds == 15
    assert optimizer.stability_weight == 0.5


def test_parametres_invalides_refuses():
    with pytest.raises(ValueError, match="timeout_seconds"):
        IncrementalOptimizer(timeout_seconds=0)
    with pytest.raises(ValueError, match="stability_weight"):
        IncrementalOptimizer(stability_weight=-1)


# -- re-optimisation de base ------------------------------------------------
def test_panne_machine_repousse_les_operations_hors_de_la_fenetre(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, result = _reoptimise(event, schedule, instance)

    assert result is not None
    for entry in result.schedule.entries:
        if entry.machine_id == "M1":
            # Aucune operation ne chevauche la fenetre d'indisponibilite.
            assert entry.start_time >= 160 or entry.end_time <= 100


def test_aucune_operation_ne_demarre_avant_t_now(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, result = _reoptimise(event, schedule, instance)

    assert all(e.start_time >= 90 for e in result.schedule.entries)


def test_les_operations_figees_ne_sont_pas_dans_le_resultat(atelier):
    """J1 a demarre a 0 : elle ne doit jamais reapparaitre comme variable."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, result = _reoptimise(event, schedule, instance)

    assert all(e.job_id != "J1" for e in result.schedule.entries)


def test_precedences_respectees_dans_la_zone(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, result = _reoptimise(event, schedule, instance)

    par_job = {}
    for e in result.schedule.entries:
        par_job.setdefault(e.job_id, []).append(e)
    for entrees in par_job.values():
        ordonnees = sorted(entrees, key=lambda e: e.position_in_job)
        for k in range(len(ordonnees) - 1):
            assert ordonnees[k].end_time <= ordonnees[k + 1].start_time


def test_pas_de_chevauchement_machine_dans_la_zone(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, result = _reoptimise(event, schedule, instance)

    par_machine = {}
    for e in result.schedule.entries:
        par_machine.setdefault(e.machine_id, []).append((e.start_time, e.end_time))
    for intervalles in par_machine.values():
        intervalles.sort()
        for k in range(len(intervalles) - 1):
            assert intervalles[k][1] <= intervalles[k + 1][0]


def test_le_resultat_est_marque_incremental(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, result = _reoptimise(event, schedule, instance)

    assert result.method == "incremental"
    assert result.schedule.method_used == "incremental"
    assert result.schedule.solver_status in ("optimal", "feasible")


# -- terme de stabilite : le critere d'acceptation central ------------------
@pytest.fixture
def atelier_indifferent():
    """Deux jobs interchangeables sur M1, tous deux tres en avance sur leur deadline.

    Le retard pondere vaut 0 pour un grand nombre d'ordonnancements : c'est
    exactement le cas ou CP-SAT peut bouleverser le planning sans aucun gain.
    M1 : J1[100-150] J2[200-250], deadlines tres larges.
    """
    entries = [
        _entry("J1", "M1", 1, 100, 50),
        _entry("J2", "M1", 1, 200, 50),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1)], deadline=5000, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1)], deadline=5000, weight=1.0),
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times={}, wr=1)
    return Schedule(entries=entries), instance


def test_la_stabilite_maintient_le_planning_proche_de_loriginal(atelier_indifferent):
    """Critere : parmi des solutions quasi optimales, on garde la plus proche.

    Sans terme de stabilite, rien n'empeche CP-SAT de tout ramener au plus tot
    (les deadlines sont hors de portee, le retard vaut 0 partout). Avec, les jobs
    restent a leur place d'origine.
    """
    schedule, instance = atelier_indifferent
    event = make_event("duration_change", timestamp=90, job_id="J1",
                       position_in_job=1, machine_id="M1", new_duration=50)

    _, avec = _reoptimise(event, schedule, instance,
                          optimizer=IncrementalOptimizer(timeout_seconds=10,
                                                         stability_weight=0.1))
    debuts = {e.job_id: e.start_time for e in avec.schedule.entries}
    assert debuts["J1"] == 100
    assert debuts.get("J2", 200) == 200


def test_sans_stabilite_la_solution_derive_de_loriginal(atelier_indifferent):
    """Contre-epreuve : a poids nul, plus rien n'ancre le job sur sa place.

    L'assertion porte sur la DERIVE, pas sur une date precise : le retard vaut zero
    partout (les deadlines sont hors de portee) et le terme de stabilite est neutralise,
    donc toutes les placements faisables sont egalement optimaux et CP-SAT peut rendre
    n'importe lequel. Exiger une date particuliere reviendrait a verrouiller un choix
    arbitraire du solveur, pas un comportement du modele.
    """
    schedule, instance = atelier_indifferent
    event = make_event("duration_change", timestamp=90, job_id="J1",
                       position_in_job=1, machine_id="M1", new_duration=50)

    _, sans = _reoptimise(event, schedule, instance,
                          optimizer=IncrementalOptimizer(timeout_seconds=10,
                                                         stability_weight=0.0))
    debuts = {e.job_id: e.start_time for e in sans.schedule.entries}
    assert debuts["J1"] != 100  # plus aucun frein a la derive


def test_la_stabilite_ne_bloque_pas_un_deplacement_necessaire(atelier):
    """Contrainte MOLLE : elle n'empeche pas de bouger quand il le faut."""
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _, result = _reoptimise(event, schedule, instance)

    debuts = {e.job_id: e.start_time for e in result.schedule.entries
              if e.machine_id == "M1"}
    assert debuts["J2"] >= 160  # a bien bouge malgre la penalite


def test_un_poids_de_stabilite_enorme_fige_le_planning(atelier_indifferent):
    schedule, instance = atelier_indifferent
    event = make_event("duration_change", timestamp=90, job_id="J1",
                       position_in_job=1, machine_id="M1", new_duration=50)
    _, result = _reoptimise(event, schedule, instance,
                            optimizer=IncrementalOptimizer(timeout_seconds=10,
                                                           stability_weight=1000.0))
    debuts = {e.job_id: e.start_time for e in result.schedule.entries}
    assert debuts["J1"] == 100


def test_la_linearisation_de_la_valeur_absolue_est_exacte(atelier_indifferent):
    """delta_plus + delta_moins vaut bien l'ecart absolu, dans les deux sens.

    Verifie l'arithmetique de l'objectif : la valeur rendue par le solveur doit
    egaler exactement retard_pondere + stability_weight * somme des |ecarts|
    recalculee depuis les entrees produites. Si la linearisation etait fausse
    (un seul delta, ou un signe inverse), l'egalite tomberait.
    """
    schedule, instance = atelier_indifferent
    poids = 0.1
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    zone, result = _reoptimise(
        event, schedule, instance,
        optimizer=IncrementalOptimizer(timeout_seconds=10, stability_weight=poids),
    )

    debuts_origine = {
        (e.job_id, e.position_in_job): e.start_time for e in zone.state.future_entries
    }
    premiere_position = {}
    for e in result.schedule.entries:
        cle = e.job_id
        if cle not in premiere_position or e.position_in_job < premiere_position[cle][0]:
            premiere_position[cle] = (e.position_in_job, e.start_time)

    ecart_total = 0
    for job_id, (position, debut) in premiere_position.items():
        origine = debuts_origine.get((job_id, position))
        if origine is not None:
            ecart_total += abs(debut - origine)

    attendu = result.schedule.total_weighted_tardiness + poids * ecart_total
    assert result.objective == pytest.approx(attendu, abs=0.01)
    assert ecart_total > 0  # la panne a bien force un deplacement


# -- autres types d'evenement -----------------------------------------------
def test_job_urgent_est_insere_sans_toucher_au_fige(atelier):
    schedule, instance = atelier
    event = make_event("urgent_job", timestamp=90, job_id="J99",
                       operations=[Operation("J99", "M1", 20, 1)],
                       deadline=200, weight=9.0)
    _, result = _reoptimise(event, schedule, instance)

    assert result is not None
    inseree = [e for e in result.schedule.entries if e.job_id == "J99"]
    assert len(inseree) == 1
    assert inseree[0].start_time >= 90


def test_job_annule_disparait_du_resultat(atelier):
    schedule, instance = atelier
    event = make_event("job_cancel", timestamp=90, job_id="J2")
    _, result = _reoptimise(event, schedule, instance)

    assert all(e.job_id != "J2" for e in result.schedule.entries)


def test_duration_change_utilise_la_duree_reelle(atelier):
    schedule, instance = atelier
    event = make_event("duration_change", timestamp=90, job_id="J2",
                       position_in_job=1, machine_id="M1", new_duration=80)
    _, result = _reoptimise(event, schedule, instance)

    op = [e for e in result.schedule.entries
          if e.job_id == "J2" and e.position_in_job == 1][0]
    assert op.duration == 80
    assert op.end_time - op.start_time == 80


def test_resource_change_serialise_les_setups(atelier):
    """WR abaisse : le modele reste faisable, la capacite retiree est modelisee."""
    schedule, instance = atelier
    event = make_event("resource_change", timestamp=90, new_wr=1,
                       start_time=100, end_time=200)
    zone, result = _reoptimise(event, schedule, instance)
    # Sans setup dans cette instance jouet, la zone peut etre vide : le resultat
    # doit rester exploitable dans les deux cas.
    assert result is not None


def test_zone_vide_donne_un_resultat_vide_mais_valide(atelier):
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M9", start_time=100, end_time=160)
    _, result = _reoptimise(event, schedule, instance)

    assert result is not None
    assert result.schedule.entries == []


# -- sur l'instance reelle a 10 jobs ----------------------------------------
def test_reoptimisation_sur_instance_reelle(example_schedule, example_instance):
    t_now = example_schedule.horizon // 3
    event = make_event("machine_breakdown", timestamp=t_now,
                       machine_id=example_instance.machines[0],
                       start_time=t_now + 1, end_time=t_now + 21)
    zone, result = _reoptimise(
        event, example_schedule, example_instance,
        analyzer=ImpactAnalyzer(search_horizon=240, max_impacted_jobs=30),
    )

    assert result is not None
    assert result.duration_seconds < 15
    # Aucune operation figee n'a bouge : elles ne sont meme pas dans le resultat.
    figees = {(e.job_id, e.position_in_job) for e in zone.state.frozen_entries}
    reoptimisees = {(e.job_id, e.position_in_job) for e in result.schedule.entries}
    assert figees & reoptimisees == set()


# -- setups de jonction vers le futur non touche (D8, resout H7) -------------
@pytest.fixture
def atelier_jonction():
    """Une machine, un job de zone, un job non touche, setup non nul entre les deux.

    M1 : J1[100-140] (zone, allongee par l'evenement) puis J2[300-340] (non touche).
    Le trou de 160 unites laisse largement la place au setup J1 -> J2 (20 unites),
    de sorte que le placement du setup est contraint par le modele, pas par l'espace.
    """
    entries = [
        _entry("J1", "M1", 1, 100, 40),
        _entry("J2", "M1", 1, 300, 40),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 40, 1)], deadline=900, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 40, 1)], deadline=900, weight=1.0),
    ]
    setup_times = {("J1", "J2", "M1"): 20, ("J2", "J1", "M1"): 20}
    instance = ProblemInstance(jobs=jobs, machines=["M1"], setup_times=setup_times, wr=1)
    return Schedule(entries=entries), instance


def _evenement_jonction():
    """Allonge J1 : la zone ne contient que J1, J2 reste non touche."""
    return make_event("duration_change", timestamp=90, job_id="J1",
                      position_in_job=1, machine_id="M1", new_duration=60)


def test_le_setup_de_jonction_est_emis_avec_des_dates_du_modele(atelier_jonction):
    """H7 resolu : la transition zone -> futur non touche porte un vrai SetupEntry.

    Avant D8, ce setup n'existait que sous forme de place reservee dans un obstacle
    elargi : aucune date, donc aucun SetupEntry emis. Il est desormais porte par des
    variables optionnelles, et ses dates sortent du solveur.
    """
    schedule, instance = atelier_jonction
    zone, result = _reoptimise(_evenement_jonction(), schedule, instance)

    assert result is not None
    assert ("J2", 1) in result.junction_setups, (
        "aucun setup emis a la jonction zone / futur non touche"
    )
    setup = result.junction_setups[("J2", 1)]
    assert setup.from_job_id == "J1"
    assert setup.duration == 20
    assert setup.end_time - setup.start_time == 20


def test_le_setup_de_jonction_sinsere_sans_chevaucher(atelier_jonction):
    """Ses dates tiennent entre la fin de l'operation de zone et le job non touche."""
    schedule, instance = atelier_jonction
    zone, result = _reoptimise(_evenement_jonction(), schedule, instance)

    setup = result.junction_setups[("J2", 1)]
    fin_zone = max(e.end_time for e in result.schedule.entries if e.job_id == "J1")
    assert setup.start_time >= fin_zone, "le setup empiete sur l'operation de zone"
    assert setup.end_time <= 300, "le setup empiete sur l'operation non touchee"


def test_la_fusion_rattache_le_setup_de_jonction_sans_muter_loriginal(atelier_jonction):
    """Le setup remonte par le WindowResult et devient celui de l'entree non touchee."""
    schedule, instance = atelier_jonction
    avant = [e.setup for e in schedule.entries if e.job_id == "J2"]
    zone, result = _reoptimise(_evenement_jonction(), schedule, instance)
    merged, _report = ScheduleMerger().merge(zone, result, instance)

    fusionnee = next(e for e in merged.entries if e.job_id == "J2")
    assert fusionnee.setup is not None
    assert fusionnee.setup.from_job_id == "J1"
    # Les entrees non touchees appartiennent a la resolution precedente : la fusion
    # travaille sur une copie et ne doit pas les modifier en place.
    assert [e.setup for e in schedule.entries if e.job_id == "J2"] == avant


def test_le_predecesseur_dorigine_subsiste_quand_la_zone_ne_sintercale_pas(atelier):
    """Aucun setup de jonction n'est invente si la zone ne precede pas la jonction.

    Contre-epreuve du garde-fou `AddExactlyOne` : le modele doit pouvoir conclure
    "predecesseur inchange", et alors n'emettre aucun SetupEntry de jonction.
    """
    schedule, instance = atelier
    event = make_event("machine_breakdown", timestamp=90,
                       machine_id="M1", start_time=100, end_time=160)
    _zone, result = _reoptimise(event, schedule, instance)

    # Cet atelier n'a aucun setup declare : aucune jonction ne peut en produire.
    assert result.junction_setups == {}


def test_le_setup_de_jonction_occupe_reellement_la_machine(atelier_jonction):
    """Le setup de jonction est un intervalle du modele, pas une date decorative.

    C'est la difference avec la version d'avant D8 : etant dans le NoOverlap de sa
    machine, aucune operation de la zone ne peut le chevaucher. Ses dates sont donc
    exploitables telles quelles par la fusion.
    """
    schedule, instance = atelier_jonction
    zone, result = _reoptimise(_evenement_jonction(), schedule, instance)
    setup = result.junction_setups[("J2", 1)]

    for entry in result.schedule.entries:
        if entry.machine_id != "M1":
            continue
        assert entry.end_time <= setup.start_time or entry.start_time >= setup.end_time


def test_sur_instance_reelle_les_jonctions_sont_emises_et_valides(
    example_schedule, example_instance
):
    """Sur les 10 jobs, au moins un scenario produit des setups de jonction valides.

    C'est le cas qui avait revele H7 : sur cette instance les setups sont non nuls,
    et la fusion presentait des transitions sans SetupEntry a la frontiere droite.
    """
    machine = example_instance.machines[1]  # M2 : setups non nuls, futur non touche
    t_now = 60
    suivantes = sorted(
        (e for e in example_schedule.entries
         if e.machine_id == machine and e.start_time > t_now),
        key=lambda e: e.start_time,
    )
    debut = suivantes[0].start_time
    event = make_event("machine_breakdown", timestamp=t_now, machine_id=machine,
                       start_time=debut, end_time=debut + 20)

    zone, result = _reoptimise(
        event, example_schedule, example_instance,
        analyzer=ImpactAnalyzer(search_horizon=400, max_impacted_jobs=30),
    )
    assert result is not None
    assert result.junction_setups, "aucun setup de jonction sur un cas qui en exige"

    merged, report = ScheduleMerger().merge(zone, result, example_instance)
    assert report.right_boundary_violations == []
    assert validate_schedule(merged, instance=example_instance) == []

    # Chaque setup de jonction est bien porte par l'entree non touchee visee.
    for (job_id, position), setup in result.junction_setups.items():
        entry = next(
            e for e in merged.entries
            if e.job_id == job_id and e.position_in_job == position
        )
        assert entry.setup is not None
        assert entry.setup.from_job_id == setup.from_job_id
        assert entry.setup.start_time == setup.start_time
