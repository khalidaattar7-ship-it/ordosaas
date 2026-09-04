"""
Scenarios cibles sur les jonctions zone / futur non touche.

Livrable 1 de la Discussion 2. Ce module verrouille le comportement aux frontieres
entre une operation de la zone reoptimisee et une entree non touchee, dans les DEUX
sens de transition :

    [zone] --garde amont--> [non touchee] --garde aval--> [zone]

Il porte deux constats distincts, a ne pas confondre :

- **Constat A** (limite connue, confirmee benigne — cf. D8) : une entree non touchee
  au-dela de la premiere de sa machine conserve son `SetupEntry` d'origine. Aucun
  chevauchement n'en decoule, mais ses metadonnees (`from_job_id`, `duration`)
  peuvent etre perimees. Verrouille ici pour que cette limite reste *constatee*, pas
  seulement affirmee.
- **Constat B** (defaut reel, corrige — cf. D10) : avant correction, une operation de
  la zone pouvait se coller a la fin d'une entree non touchee sans laisser la place a
  son setup entrant. Le planning etait infaisable en atelier tout en passant le
  validateur canonique, qui ne verifie ni le predecesseur reel d'un setup ni sa duree.

Les scenarios sont construits pour etre DETERMINISTES : la geometrie du planning, et
non un alea de CP-SAT, force le placement recherche.
"""
import pytest

from scheduling.incremental import IncrementalConfig, resolve_incremental
from scheduling.validation import validate_schedule
from tests.scenarios_jonction import (
    zone_derriere_une_non_touchee,
    zone_derriere_une_non_touchee_non_jonction,
    zone_encadree_par_deux_non_touchees,
    zone_intercalee_entre_deux_non_touchees,
)


def _sur_machine(schedule, machine_id):
    """Entrees d'une machine, dans l'ordre chronologique des operations."""
    return sorted(
        (e for e in schedule.entries if e.machine_id == machine_id),
        key=lambda e: e.start_time,
    )


def _config(**kwargs):
    """Bornes absolues : ces scenarios testent les jonctions, pas le dimensionnement.

    Le dimensionnement de la zone (fractions relatives, cf. D7) est couvert par
    tests/test_impact_analyzer.py — le figer ici rendrait ces tests sensibles a un
    futur ajustement des fractions par defaut.
    """
    base = dict(search_horizon=10_000, max_impacted_jobs=50, timeout_seconds=10)
    base.update(kwargs)
    return IncrementalConfig(**base)


# ==========================================================================
# Constat B — defaut reel : la place du setup ENTRANT d'une operation de zone
# ==========================================================================
@pytest.fixture
def scenario_derriere():
    """Constat B, cas de base. Defini dans tests/scenarios_jonction.py.

    Les scenarios vivent dans un module partage pour que le script de validation
    (`python -m tests.validate_incremental`) rejoue exactement les memes, sans
    risque de divergence entre la suite de tests et le script.
    """
    return zone_derriere_une_non_touchee()


def test_la_place_du_setup_entrant_est_reservee_derriere_une_non_touchee(
    scenario_derriere
):
    """Non-regression du defaut trouve par le livrable 1 (Constat B, cf. D10).

    Avant la garde aval, J3 etait place a 150, colle a la fin de J1, alors que la
    transition exige 40 unites de setup : le planning etait infaisable en atelier
    tout en passant `validate_schedule`. La garde aval reserve desormais cette place.
    """
    schedule, instance, event = scenario_derriere
    resolution = resolve_incremental(
        schedule, event, instance,
        # Stabilite neutralisee : rien n'ancre plus J3, le solveur est libre de la
        # coller a J1. C'est la configuration qui revelait le defaut.
        config=_config(stability_weight=0.0),
    )

    j1, j3 = _sur_machine(resolution.schedule, "M1")[:2]
    assert j1.job_id == "J1" and j3.job_id == "J3"

    espace = j3.start_time - j1.end_time
    requis = instance.get_setup("J1", "J3", "M1")
    assert espace >= requis, (
        f"setup entrant J1->J3 de {requis} unites, mais seulement {espace} "
        f"unites libres entre la fin de J1 ({j1.end_time}) et le debut de J3 "
        f"({j3.start_time}) : planning infaisable en atelier"
    )


def test_le_planning_reste_valide_et_la_zone_est_bien_derriere(scenario_derriere):
    """Le scenario teste bien ce qu'il pretend : J3 est apres J1, et tout est valide."""
    schedule, instance, event = scenario_derriere
    resolution = resolve_incremental(
        schedule, event, instance, config=_config(stability_weight=0.0)
    )

    assert sorted(resolution.zone.impacted_job_ids) == ["J3"]
    j1, j3 = _sur_machine(resolution.schedule, "M1")[:2]
    assert j3.start_time > j1.end_time, "J3 devait se placer derriere J1"
    assert validate_schedule(resolution.schedule, instance=instance) == []
    assert resolution.is_clean


def test_la_garde_aval_vaut_aussi_pour_une_non_touchee_non_jonction():
    """Le defaut ne se limitait pas a l'entree de jonction, le correctif non plus.

    M1 : J0[60-90] (jonction) puis J1[100-150] (non touchee ordinaire), et J3 de la
    zone qui veut se coller derriere J1. C'est le second cas ou le defaut avait ete
    reproduit avant correction.
    """
    schedule, instance, event = zone_derriere_une_non_touchee_non_jonction()
    resolution = resolve_incremental(
        schedule, event, instance, config=_config(stability_weight=0.0)
    )

    ordre = _sur_machine(resolution.schedule, "M1")
    for precedente, suivante in zip(ordre, ordre[1:]):
        requis = instance.get_setup(precedente.job_id, suivante.job_id, "M1")
        espace = suivante.start_time - precedente.end_time
        assert espace >= requis, (
            f"transition {precedente.job_id}->{suivante.job_id} : "
            f"{espace} unites libres pour un setup de {requis}"
        )


def test_les_deux_sens_de_transition_sont_gardes():
    """Confirmation explicite que l'amont ET l'aval sont couverts (cf. D10).

    Une zone encadree par deux entrees non touchees sur la meme machine. Les deux
    transitions exigent un setup non nul, et les deux doivent avoir leur place
    reservee — celle en amont de J2 par la garde amont preexistante, celle en aval
    de J1 par la garde aval ajoutee en D10.
    """
    schedule, instance, event = zone_encadree_par_deux_non_touchees()
    resolution = resolve_incremental(
        schedule, event, instance, config=_config(stability_weight=0.0)
    )

    ordre = _sur_machine(resolution.schedule, "M1")
    assert [e.job_id for e in ordre] == ["J1", "J3", "J2"], (
        "le scenario suppose la zone encadree par les deux entrees non touchees"
    )
    aval = ordre[1].start_time - ordre[0].end_time
    amont = ordre[2].start_time - ordre[1].end_time
    assert aval >= instance.get_setup("J1", "J3", "M1"), "garde aval insuffisante"
    assert amont >= instance.get_setup("J3", "J2", "M1"), "garde amont insuffisante"
    assert validate_schedule(resolution.schedule, instance=instance) == []


# ==========================================================================
# Constat A — limite connue, confirmee benigne
# ==========================================================================
@pytest.fixture
def scenario_intercale():
    """Constat A. Defini dans tests/scenarios_jonction.py."""
    return zone_intercalee_entre_deux_non_touchees()


def test_la_zone_sintercale_bien_entre_deux_entrees_non_touchees(
    scenario_intercale
):
    """Le scenario reproduit bien le cas vise : ni J1 ni J2 ne sont dans la zone."""
    schedule, instance, event = scenario_intercale
    resolution = resolve_incremental(schedule, event, instance, config=_config())

    assert sorted(resolution.zone.impacted_job_ids) == ["J3"]
    non_touchees = {e.job_id for e in resolution.zone.untouched_future_entries}
    assert non_touchees == {"J1", "J2"}
    assert [e.job_id for e in _sur_machine(resolution.schedule, "M1")] == \
        ["J1", "J3", "J2"]


def test_la_reservation_conservatrice_evite_tout_chevauchement(scenario_intercale):
    """Constat A confirme BENIN pour la validite : aucun chevauchement n'apparait.

    C'est le coeur du livrable 1 : la limite de D8 laisse une metadonnee perimee,
    mais la reservation conservatrice fait son office et le planning reste valide
    et executable.
    """
    schedule, instance, event = scenario_intercale
    resolution = resolve_incremental(schedule, event, instance, config=_config())

    assert validate_schedule(resolution.schedule, instance=instance) == []
    assert resolution.report.left_boundary_violations == []
    assert resolution.report.right_boundary_violations == []

    # La place du setup reellement en vigueur (J3 -> J2, 30 unites) existe bien.
    ordre = _sur_machine(resolution.schedule, "M1")
    j3, j2 = ordre[1], ordre[2]
    assert j2.start_time - j3.end_time >= instance.get_setup("J3", "J2", "M1")


def test_la_metadonnee_de_setup_peut_rester_perimee_au_dela_de_la_jonction(
    scenario_intercale
):
    """Constat A verrouille tel qu'observe : `from_job_id` et `duration` perimes.

    Ce test CONSTATE la limite au lieu de l'affirmer. Il echouera le jour ou elle
    sera levee — ce sera alors le signal de mettre a jour D8/D10, et non de
    contourner le test.

    Seule la POSITION TEMPORELLE du SetupEntry reste fiable dans ce cas : elle tombe
    dans une zone reservee, donc sans chevauchement. Ni `from_job_id` ni `duration`
    ne doivent etre consommes tels quels par la Discussion 4 (diff, endpoints).
    """
    schedule, instance, event = scenario_intercale
    resolution = resolve_incremental(schedule, event, instance, config=_config())

    j2 = next(e for e in resolution.schedule.entries if e.job_id == "J2")
    assert j2.setup is not None
    # Le predecesseur reel est J3, mais le setup nomme encore J1...
    assert j2.setup.from_job_id == "J1"
    # ... et porte la duree de l'ancienne transition, pas de la nouvelle.
    assert j2.setup.duration == instance.get_setup("J1", "J2", "M1") == 20
    assert instance.get_setup("J3", "J2", "M1") == 30

    # La jonction, elle, est bien traitee par D8 : aucun setup perime sur J1.
    j1 = next(e for e in resolution.schedule.entries if e.job_id == "J1")
    assert j1.setup is None
