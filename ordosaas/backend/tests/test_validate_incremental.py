"""
Tests du script de validation incremental (livrable 3 de la Discussion 2).

Un script de validation qui ne detecte rien ne vaut rien : ces tests verifient
surtout sa SENSIBILITE — qu'il echoue bien quand on lui presente un planning
reellement fautif — et pas seulement qu'il passe sur des cas sains.
"""
from dataclasses import replace

import pytest

from scheduling.incremental import IncrementalConfig, resolve_incremental
from scheduling.models.perturbation import make_event
from tests.scenarios_jonction import (
    SCENARIOS,
    zone_derriere_une_non_touchee,
    zone_devant_la_jonction,
    zone_intercalee_entre_deux_non_touchees,
)
from tests.validate_incremental import (
    FAIL,
    INFO,
    PASS,
    RapportValidation,
    valide_resolution,
)


def _config(**kwargs):
    base = dict(search_horizon=10_000, max_impacted_jobs=50, timeout_seconds=10,
                stability_weight=0.0)
    base.update(kwargs)
    return IncrementalConfig(**base)


def _resout(constructeur, **kwargs):
    schedule, instance, event = constructeur()
    resolution = resolve_incremental(schedule, event, instance, config=_config(**kwargs))
    return schedule, instance, event, resolution


def _verif(rapport, fragment):
    """La verification dont le nom contient `fragment`."""
    for v in rapport.verifications:
        if fragment in v.nom:
            return v
    raise AssertionError(
        f"aucune verification ne contient {fragment!r} ; "
        f"presentes : {[v.nom for v in rapport.verifications]}"
    )


# -- comportement nominal ----------------------------------------------------
@pytest.mark.parametrize("nom", sorted(SCENARIOS))
def test_les_scenarios_du_livrable_1_passent_toutes_les_verifications(nom):
    """Le script tourne sur les scenarios du livrable 1 sans modification."""
    schedule, instance, event, resolution = _resout(SCENARIOS[nom])
    rapport = valide_resolution(schedule, event, resolution, instance, scenario=nom)

    echecs = [v.nom for v in rapport.verifications if v.echoue]
    assert echecs == [], f"{nom} : {echecs}"
    assert rapport.ok


def test_le_rapport_expose_chaque_verification_separement():
    """PASS/FAIL par verification, pas un booleen global."""
    schedule, instance, event, resolution = _resout(zone_derriere_une_non_touchee)
    rapport = valide_resolution(schedule, event, resolution, instance)

    assert len(rapport.verifications) >= 5
    assert all(v.statut in (PASS, FAIL, INFO) for v in rapport.verifications)
    for fragment in ("Operations figees", "Frontieres", "Setups de jonction",
                     "Place reservee", "derive hors zone", "repli"):
        _verif(rapport, fragment)


def test_la_limite_benigne_est_signalee_en_info_pas_en_echec():
    """Constat A : metadonnee perimee -> INFO, jamais FAIL.

    C'est la distinction que le script doit tenir : une limite documentee et sans
    effet sur la validite ne doit pas se confondre avec un defaut.
    """
    schedule, instance, event, resolution = _resout(
        zone_intercalee_entre_deux_non_touchees
    )
    rapport = valide_resolution(schedule, event, resolution, instance)

    perime = _verif(rapport, "perimees")
    assert perime.statut == INFO
    assert rapport.ok


# -- sensibilite : le script doit ATTRAPER les fautes ------------------------
def test_il_detecte_une_operation_figee_deplacee():
    """Falsification directe de l'invariant central."""
    schedule, instance, event, resolution = _resout(zone_derriere_une_non_touchee)
    # On fabrique une operation figee de toutes pieces, puis on la deplace dans le
    # planning fusionne : le script doit s'en apercevoir.
    figee = replace(resolution.schedule.entries[0], start_time=0, end_time=10)
    resolution.zone.state.frozen_entries.append(resolution.schedule.entries[0])
    resolution.schedule.entries[0] = figee

    rapport = valide_resolution(schedule, event, resolution, instance)
    verif = _verif(rapport, "Operations figees")
    assert verif.statut == FAIL
    assert not rapport.ok


def test_il_detecte_un_setup_de_jonction_incoherent():
    """Duree faussee sur un setup de jonction emis."""
    schedule, instance, event, resolution = _resout(zone_devant_la_jonction)
    assert resolution.junction_setups, (
        "ce scenario doit emettre un setup de jonction, sinon il ne teste rien"
    )

    cle = next(iter(resolution.junction_setups))
    setup = resolution.junction_setups[cle]
    resolution.junction_setups[cle] = replace(setup, duration=setup.duration + 7)

    rapport = valide_resolution(schedule, event, resolution, instance)
    assert _verif(rapport, "Setups de jonction").statut == FAIL


def test_il_detecte_une_place_de_setup_insuffisante():
    """LE controle qui aurait attrape le defaut corrige en D10.

    On recolle une operation de la zone contre l'entree non touchee qui la precede,
    ce que la garde aval interdit desormais : le script doit le signaler.
    """
    schedule, instance, event, resolution = _resout(zone_derriere_une_non_touchee)

    j1 = next(e for e in resolution.schedule.entries if e.job_id == "J1")
    index = next(i for i, e in enumerate(resolution.schedule.entries)
                 if e.job_id == "J3")
    j3 = resolution.schedule.entries[index]
    resolution.schedule.entries[index] = replace(
        j3, start_time=j1.end_time, end_time=j1.end_time + j3.duration
    )

    rapport = valide_resolution(schedule, event, resolution, instance)
    verif = _verif(rapport, "Place reservee")
    assert verif.statut == FAIL
    assert any("J1->J3" in d for d in verif.details)


def test_il_detecte_une_derive_hors_zone():
    """Un job deplace alors qu'il n'appartient pas a la zone d'impact."""
    schedule, instance, event, resolution = _resout(zone_derriere_une_non_touchee)

    index = next(i for i, e in enumerate(resolution.schedule.entries)
                 if e.job_id == "J1")
    j1 = resolution.schedule.entries[index]
    resolution.schedule.entries[index] = replace(
        j1, start_time=j1.start_time + 500, end_time=j1.end_time + 500
    )

    rapport = valide_resolution(schedule, event, resolution, instance)
    verif = _verif(rapport, "derive hors zone")
    assert verif.statut == FAIL
    assert any("J1" in d for d in verif.details)


def test_il_detecte_un_routage_du_garde_fou():
    """Contrat H5 : le garde-fou signale, il ne route jamais vers le LNS."""
    schedule, instance, event, resolution = _resout(
        zone_derriere_une_non_touchee, fallback_threshold=0.01
    )
    if not resolution.fallback_recommended:
        pytest.skip("le seuil n'a pas ete franchi sur ce scenario")

    resolution.schedule.method_used = "lns"
    rapport = valide_resolution(schedule, event, resolution, instance)
    verif = _verif(rapport, "non route")
    assert verif.statut == FAIL
    assert any("routage detecte" in d for d in verif.details)


# -- distinction entre defaut de l'incremental et heritage -------------------
def test_les_transitions_heritees_ne_sont_pas_imputees_a_lincremental(
    example_schedule, example_instance
):
    """Cadrage de perimetre : H8 n'est pas un echec de l'incremental.

    Le planning initial ne reserve aucune place aux setups (H8). Ces transitions
    heritees doivent apparaitre en INFO et ne jamais faire echouer la validation de
    l'incremental, qui n'en est pas responsable.
    """
    t_now = example_schedule.horizon // 3
    machine = example_instance.machines[0]
    suivantes = sorted(
        (e for e in example_schedule.entries
         if e.machine_id == machine and e.start_time > t_now),
        key=lambda e: e.start_time,
    )
    event = make_event("machine_breakdown", timestamp=t_now, machine_id=machine,
                       start_time=suivantes[0].start_time,
                       end_time=suivantes[0].start_time + 20)
    resolution = resolve_incremental(
        example_schedule, event, example_instance, t_now=t_now,
        config=IncrementalConfig(timeout_seconds=12),
    )
    rapport = valide_resolution(
        example_schedule, event, resolution, example_instance, t_now=t_now
    )

    heritees = _verif(rapport, "heritees du planning initial")
    assert heritees.statut == INFO
    assert any("H8" in d for d in heritees.details)


def test_le_rapport_saffiche_sans_erreur(capsys):
    """Le rendu console doit rester lisible et ne rien lever."""
    schedule, instance, event, resolution = _resout(zone_derriere_une_non_touchee)
    rapport = valide_resolution(schedule, event, resolution, instance,
                                scenario="scenario de test")
    rapport.affiche()

    sortie = capsys.readouterr().out
    assert "=== scenario de test ===" in sortie
    assert "[PASS]" in sortie
    assert "--> OK" in sortie


def test_un_rapport_vide_est_ok():
    """Cas degenere : aucune verification, donc aucun echec."""
    assert RapportValidation(scenario="vide").ok
    assert RapportValidation(scenario="vide").nb_echecs == 0
