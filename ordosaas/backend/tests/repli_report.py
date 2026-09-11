"""
Validation du signal de repli contre la matrice densite x perturbation.

Livrable 3 de la session D13. Usage :

    python -m tests.repli_report            # console + docs/repli-signal.md
    python -m tests.repli_report --console  # console uniquement

Rejoue les 9 cellules de la matrice recalibree de la Discussion 2 et repond a une
seule question : **en configuration de PRODUCTION (bornes D7 actives), le repli se
declenche-t-il maintenant la ou la cascade reelle le justifie ?**

Pour chaque cellule, trois colonnes se comparent :

- `cascade naturelle` — l'ampleur reelle, mesuree bornes relachees ;
- `AVANT D13` — ce que donnait la regle d'origine (ratio mesure > seuil) en
  production. Structurellement toujours faux, le plafond de 20 % etant sous le
  seuil de 50 % ;
- `APRES D13` — le signal de troncature active.
"""
import logging
import os
import sys

from scheduling.incremental import resolve_incremental
from tests.densite_report import REGIMES, _perturbations
from tests.densite_variants import DENSITES, construit_variantes

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
RAPPORT = os.path.join(DOCS_DIR, "repli-signal.md")


def collecte() -> list:
    """Les 9 cellules, mesurees dans les deux regimes."""
    variantes = construit_variantes()
    lignes = []

    for nom in DENSITES:
        schedule, instance = variantes[nom]
        t_now = schedule.horizon // 3

        for libelle, event in _perturbations(schedule, instance, t_now):
            mesures = {}
            for regime, config in REGIMES.items():
                resolution = resolve_incremental(
                    schedule, event, instance, t_now=t_now, config=config
                )
                zone = resolution.zone
                mesures[regime] = {
                    "pct": round(100 * zone.ratio_future_jobs_affected),
                    "jobs": zone.nb_impacted_jobs,
                    "futurs": zone.nb_future_jobs,
                    "tronquee": zone.truncated,
                    "active": zone.truncated_before_convergence,
                    "repli": zone.fallback_recommended,
                    "seuil": config.fallback_threshold or 0.5,
                }

            prod = mesures["production"]
            # La regle d'origine, telle qu'elle se serait comportee : le ratio seul.
            prod["repli_avant"] = prod["pct"] / 100 > prod["seuil"]
            lignes.append({
                "densite": nom,
                "perturbation": libelle,
                "naturelle": mesures["cascade_naturelle"],
                "production": prod,
            })
    return lignes


def _oui_non(v, gras=True):
    if v is None:
        return "—"
    if not v:
        return "non"
    return "**oui**" if gras else "oui"


def rendu_markdown(lignes) -> str:
    out = [
        "# Validation du signal de repli — D13",
        "",
        "> Généré par `python -m tests.repli_report` (livrable 3 de la session D13).",
        "",
        "## La question posée",
        "",
        "D7 borne la recherche à 20 % des jobs futurs ; H5 déclenche le repli à 50 %.",
        "**20 % < 50 %** : le plafond coupait donc toujours la zone avant que le seuil",
        "puisse la voir. Des cascades réelles de 71 % et 100 % passaient inaperçues.",
        "",
        "Ce rapport vérifie que le signal de troncature active (D13) déclenche",
        "désormais le repli là où la cascade réelle le justifie — **et seulement là**.",
        "",
        "## Résultat, cellule par cellule",
        "",
        "| Densité | Perturbation | Cascade naturelle | Zone en production | Tronquée | Propagation active | AVANT D13 | APRÈS D13 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for l in lignes:
        n, p = l["naturelle"], l["production"]
        out.append(
            f"| {l['densite']} | {l['perturbation']} | "
            f"{n['jobs']}/{n['futurs']} — **{n['pct']} %** | "
            f"{p['jobs']}/{p['futurs']} — {p['pct']} % | "
            f"{_oui_non(p['tronquee'], gras=False)} | {_oui_non(p['active'])} | "
            f"{_oui_non(p['repli_avant'])} | {_oui_non(p['repli'])} |"
        )

    out += ["", "## Lecture", ""] + _observations(lignes)
    return "\n".join(out) + "\n"


def _observations(lignes) -> list:
    avant = [l for l in lignes if l["production"]["repli_avant"]]
    apres = [l for l in lignes if l["production"]["repli"]]
    obs = [
        f"- **Avant D13** : {len(avant)} cellule(s) sur {len(lignes)} déclenchaient le "
        f"repli en production. C'est le défaut : structurellement impossible tant que "
        f"le plafond de D7 (20 %) reste sous le seuil de H5 (50 %).",
        f"- **Après D13** : {len(apres)} cellule(s) sur {len(lignes)} le déclenchent.",
        "",
    ]

    if apres:
        obs.append("Cellules qui déclenchent désormais le repli :")
        obs.append("")
        for l in apres:
            n = l["naturelle"]
            obs.append(
                f"- `{l['densite']} / {l['perturbation']}` — cascade réelle "
                f"**{n['pct']} %** des jobs futurs, zone tronquée à "
                f"{l['production']['pct']} % en production."
            )
        obs.append("")

    # Verification qualitative : correlation avec le seuil sur la cascade reelle.
    attendus = {
        (l["densite"], l["perturbation"]) for l in lignes
        if l["naturelle"]["pct"] / 100 > l["naturelle"]["seuil"]
    }
    obtenus = {(l["densite"], l["perturbation"]) for l in apres}
    if attendus == obtenus:
        obs.append(
            "**Le signal correspond exactement à l'attente qualitative** : il se "
            "déclenche sur les cellules — et uniquement celles — dont la cascade "
            "réelle dépasse le seuil de repli, alors même que la zone mesurée en "
            "production reste très en-dessous."
        )
    else:
        manques = sorted(attendus - obtenus)
        exces = sorted(obtenus - attendus)
        if manques:
            obs.append(
                f"- ⚠️ **Faux négatifs** — cascade réelle au-dessus du seuil sans "
                f"déclenchement : {', '.join(f'{d} / {p}' for d, p in manques)}."
            )
        if exces:
            obs.append(
                f"- ⚠️ **Faux positifs** — déclenchement sans que la cascade réelle "
                f"dépasse le seuil : {', '.join(f'{d} / {p}' for d, p in exces)}."
            )
    return obs


def rendu_console(lignes) -> None:
    print("=" * 100)
    print("VALIDATION DU SIGNAL DE REPLI (D13) — configuration de PRODUCTION")
    print("=" * 100)
    print()
    print(f"{'densite':10s} {'perturbation':28s} {'naturelle':>10s} {'zone prod':>10s} "
          f"{'tronq':>6s} {'active':>7s} {'AVANT':>6s} {'APRES':>6s}")
    print("-" * 100)
    for l in lignes:
        n, p = l["naturelle"], l["production"]
        print(f"{l['densite']:10s} {l['perturbation']:28s} {n['pct']:>9d}% "
              f"{p['pct']:>9d}% {('OUI' if p['tronquee'] else 'non'):>6s} "
              f"{('OUI' if p['active'] else 'non'):>7s} "
              f"{('OUI' if p['repli_avant'] else 'non'):>6s} "
              f"{('OUI' if p['repli'] else 'non'):>6s}")
    print()
    for ligne in _observations(lignes):
        if ligne:
            print("  " + ligne.replace("**", "").replace("`", "").lstrip("- "))


def main() -> int:
    logging.disable(logging.WARNING)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    lignes = collecte()
    rendu_console(lignes)

    if "--console" not in sys.argv:
        chemin = os.path.normpath(RAPPORT)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(rendu_markdown(lignes))
        print()
        print(f"Rapport ecrit dans {chemin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
