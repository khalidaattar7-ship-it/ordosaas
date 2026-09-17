"""Mesure du gap WR sur le setup de contexte gauche.

Le setup de contexte gauche (dernier job fige -> premier job replanifie) etait
emis comme `SetupEntry` — donc compte par le validateur canonique dans la
`Cumulative` WR et dans le `NoOverlap` machine — alors qu'AUCUN intervalle ne le
reservait dans le modele CP-SAT. Le solveur pouvait donc le superposer librement
a d'autres setups.

Ce script repond a la question posee : ce gap a-t-il pu affecter des resultats
DEJA produits ? Il ne suffit pas de constater que le validateur passe : il faut
mesurer la MARGE. Un gap qui ne se manifeste pas parce que WR n'est jamais sature
reste un gap, et la marge dit a quelle distance on se trouve de la manifestation.

Pour chaque scenario, on rejoue la resolution incrementale et on mesure, sur le
planning fusionne :

  - occupation_max : le plus grand nombre de setups simultanes, toutes machines
    confondues (c'est la grandeur que borne WR) ;
  - marge : wr - occupation_max ;
  - occupation pendant les fenetres de setup de contexte gauche specifiquement,
    puisque ce sont les seules que le modele ne reservait pas.

Usage :
    python -m tests.wr_gap_report
"""
import sys

from scheduling.incremental import IncrementalConfig, resolve_incremental


def _occupation_max(entries) -> tuple:
    """(occupation maximale de setups simultanes, instant ou elle est atteinte)."""
    evenements = []
    for entry in entries:
        if entry.setup and entry.setup.duration > 0:
            evenements.append((entry.setup.start_time, 1))
            evenements.append((entry.setup.end_time, -1))
    if not evenements:
        return 0, None
    # Les fins passent avant les debuts a instant egal : deux setups qui se
    # touchent ne sont pas simultanes. Meme convention que find_wr_violations.
    evenements.sort(key=lambda e: (e[0], e[1]))
    charge = pic = 0
    instant_pic = None
    for instant, delta in evenements:
        charge += delta
        if charge > pic:
            pic, instant_pic = charge, instant
    return pic, instant_pic


def _setups_gauche(schedule, contexte_gauche) -> list:
    """Les SetupEntry issus du contexte gauche : ceux venant d'un job fige."""
    resultat = []
    for entry in schedule.entries:
        if not entry.setup or entry.setup.duration <= 0:
            continue
        dernier = contexte_gauche.get(entry.machine_id)
        if dernier and entry.setup.from_job_id == dernier:
            resultat.append(entry)
    return resultat


def _occupation_pendant(entries, debut, fin) -> int:
    """Nombre max de setups simultanes sur la fenetre [debut, fin)."""
    pic = 0
    bornes = sorted({
        t for entry in entries
        if entry.setup and entry.setup.duration > 0
        for t in (entry.setup.start_time, entry.setup.end_time)
        if debut <= t < fin
    } | {debut})
    for instant in bornes:
        charge = sum(
            1 for entry in entries
            if entry.setup and entry.setup.duration > 0
            and entry.setup.start_time <= instant < entry.setup.end_time
        )
        pic = max(pic, charge)
    return pic


def mesure(nom, schedule_initial, event, instance, t_now=None, config=None) -> dict:
    config = config or IncrementalConfig(
        search_horizon=10_000, max_impacted_jobs=50,
        timeout_seconds=10, stability_weight=0.0,
    )
    kwargs = {"config": config}
    if t_now is not None:
        kwargs["t_now"] = t_now
    resolution = resolve_incremental(schedule_initial, event, instance, **kwargs)
    fusionne = resolution.schedule
    if fusionne is None:
        return {"scenario": nom, "statut": "pas de resolution"}

    contexte_gauche = {}
    zone = getattr(resolution, "zone", None)
    if zone is not None:
        for entry in zone.state.frozen_entries:
            actuel = contexte_gauche.get(entry.machine_id)
            if actuel is None:
                contexte_gauche[entry.machine_id] = entry.job_id
        # le DERNIER fige par machine, pas le premier rencontre
        par_machine = {}
        for entry in zone.state.frozen_entries:
            courant = par_machine.get(entry.machine_id)
            if courant is None or entry.end_time > courant.end_time:
                par_machine[entry.machine_id] = entry
        contexte_gauche = {m: e.job_id for m, e in par_machine.items()}

    pic, instant = _occupation_max(fusionne.entries)
    gauche = _setups_gauche(fusionne, contexte_gauche)
    pic_gauche = max(
        (_occupation_pendant(fusionne.entries, e.setup.start_time, e.setup.end_time)
         for e in gauche),
        default=0,
    )
    return {
        "scenario": nom,
        "wr": instance.wr,
        "pic": pic,
        "instant": instant,
        "marge": instance.wr - pic,
        "setups_gauche": len(gauche),
        "pic_pendant_setup_gauche": pic_gauche,
        "marge_pendant_setup_gauche": instance.wr - pic_gauche if gauche else None,
    }


def _tous_les_scenarios() -> list:
    from tests.densite_report import REGIMES, _perturbations
    from tests.densite_variants import DENSITES, construit_variantes
    from tests.scenarios_jonction import SCENARIOS

    mesures = []
    for nom, constructeur in SCENARIOS.items():
        schedule, instance, event = constructeur()
        mesures.append(mesure(f"jonction — {nom}", schedule, event, instance))

    variantes = construit_variantes()
    for nom in DENSITES:
        schedule, instance = variantes[nom]
        t_now = schedule.horizon // 3
        for libelle, event in _perturbations(schedule, instance, t_now):
            for regime, config in REGIMES.items():
                mesures.append(mesure(
                    f"densite — {nom} / {libelle} / {regime}",
                    schedule, event, instance, t_now=t_now, config=config,
                ))
    return mesures


def main() -> int:
    mesures = _tous_les_scenarios()
    print(f"{'scenario':<58} {'WR':>3} {'pic':>4} {'marge':>6} "
          f"{'sg':>3} {'pic/sg':>7} {'marge/sg':>9}")
    print("-" * 96)
    satures = 0
    avec_gauche = 0
    for m in mesures:
        if m.get("statut"):
            print(f"{m['scenario']:<58} {m['statut']}")
            continue
        if m["setups_gauche"]:
            avec_gauche += 1
        marge_sg = m["marge_pendant_setup_gauche"]
        if marge_sg is not None and marge_sg <= 0:
            satures += 1
        print(f"{m['scenario']:<58} {m['wr']:>3} {m['pic']:>4} {m['marge']:>6} "
              f"{m['setups_gauche']:>3} {m['pic_pendant_setup_gauche']:>7} "
              f"{'-' if marge_sg is None else marge_sg:>9}")
    print("-" * 96)
    print(f"{len(mesures)} scenario(s), {avec_gauche} avec au moins un setup de "
          f"contexte gauche, {satures} ou WR est sature pendant celui-ci.")
    print()
    if satures:
        print("=> Le gap a PU affecter des resultats deja produits : WR est sature "
              "pendant une fenetre de setup non reservee.")
    else:
        print("=> Aucun scenario connu ne sature WR pendant un setup de contexte "
              "gauche. Le gap est reel dans le modele mais ne s'est pas manifeste "
              "sur les scenarios deja produits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
