"""
Rapport densite x perturbation du reordonnancement incremental.

Livrable 2 de la Discussion 2. Usage :

    python -m tests.densite_report            # console + docs/densite-perturbation.md
    python -m tests.densite_report --console  # console uniquement

Ce rapport est **exploratoire et descriptif**. Il ne tranche PAS la question produit
restee ouverte en fin de Discussion 1 (conserver de la marge a l'optimisation
initiale contre relever le seuil de repli) : il fournit les donnees factuelles pour
que Khalid tranche.

Les perturbations sont appliquees en valeur ABSOLUE, identiques d'une variante a
l'autre. C'est le coeur de la mesure : une panne de 20 unites est une panne de 20
unites, que le planificateur se soit garde de la marge ou non. La question posee est
donc bien « cette marge absorbe-t-elle la perturbation ? ».
"""
import logging
import os
import sys

from scheduling.components.impact_analyzer import IncrementalNotSuitableError
from scheduling.incremental import (
    IncrementalConfig,
    IncrementalResolutionError,
    resolve_incremental,
)
from scheduling.models.perturbation import make_event
from scheduling.validation import validate_schedule
from tests.densite_variants import (
    DENSITES,
    construit_variantes,
    job_urgent_type,
    mesure_densite,
    premiere_entree_future,
)

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
RAPPORT = os.path.join(DOCS_DIR, "densite-perturbation.md")

# Amplitude de la panne et du depassement, en unites de temps absolues.
DUREE_PANNE = 20
FACTEUR_DEPASSEMENT = 1.5


# Les deux regimes de bornes mesures. Les mesurer separement est indispensable :
# avec les bornes de production, le plafond relatif (20 % de 8-9 jobs futurs, soit
# 1 a 2 jobs) tronque la zone dans TOUTES les variantes et masque entierement
# l'effet de la densite. Le second regime releve les bornes pour observer la
# cascade telle qu'elle se propage reellement — c'est elle que la densite influence.
REGIMES = {
    "production": IncrementalConfig(timeout_seconds=12),
    "cascade_naturelle": IncrementalConfig(
        timeout_seconds=12, search_horizon=10_000, max_impacted_jobs=50,
    ),
}


def _perturbations(schedule, instance, t_now):
    """Les trois types de perturbation mesures, sur chaque variante.

    La panne vise la machine goulot (celle dont l'occupation est la plus longue),
    car c'est le cas le plus defavorable et celui qui a revele le constat d'origine.
    """
    goulot = max(
        instance.machines,
        key=lambda m: sum(e.duration for e in schedule.entries if e.machine_id == m),
    )
    resultats = []

    cible = premiere_entree_future(schedule, t_now, machine_id=goulot)
    if cible is not None:
        resultats.append((
            f"panne machine ({goulot}, {DUREE_PANNE} u.)",
            make_event("machine_breakdown", timestamp=t_now, machine_id=goulot,
                       start_time=cible.start_time,
                       end_time=cible.start_time + DUREE_PANNE),
        ))

    resultats.append((
        "job urgent (2 op.)",
        make_event("urgent_job", timestamp=t_now,
                   **job_urgent_type(instance, t_now)),
    ))

    cible = premiere_entree_future(schedule, t_now)
    if cible is not None:
        resultats.append((
            f"depassement duree (x{FACTEUR_DEPASSEMENT})",
            make_event("duration_change", timestamp=t_now, job_id=cible.job_id,
                       position_in_job=cible.position_in_job,
                       machine_id=cible.machine_id,
                       new_duration=int(cible.duration * FACTEUR_DEPASSEMENT) + 1),
        ))
    return resultats


def collecte() -> dict:
    """Deroule toute la matrice densite x perturbation.

    Returns:
        {"densites": {nom: mesures}, "lignes": [dict par cellule]}
    """
    variantes = construit_variantes()
    densites, lignes = {}, []

    for nom in DENSITES:
        schedule, instance = variantes[nom]
        mesures = mesure_densite(schedule, instance)
        densites[nom] = mesures
        t_now = schedule.horizon // 3

        for libelle, event in _perturbations(schedule, instance, t_now):
            for regime, config in REGIMES.items():
                ligne = {
                    "regime": regime,
                    "densite": nom,
                    "facteur": DENSITES[nom],
                    "utilisation_pct": mesures["utilisation_pct"],
                    "perturbation": libelle,
                    "t_now": t_now,
                }
                try:
                    resolution = resolve_incremental(
                        schedule, event, instance, t_now=t_now, config=config,
                    )
                except (IncrementalResolutionError, IncrementalNotSuitableError) as exc:
                    ligne.update(erreur=type(exc).__name__, jobs_zone=None,
                                 jobs_futurs=None, pct_futurs=None, repli=None,
                                 jobs_replanifies=None, valide=None, tronquee=None,
                                 horizon_zone=None, max_jobs=None)
                else:
                    zone = resolution.zone
                    ligne.update(
                        erreur=None,
                        jobs_zone=zone.nb_impacted_jobs,
                        jobs_futurs=zone.nb_future_jobs,
                        pct_futurs=round(100 * zone.ratio_future_jobs_affected),
                        repli=zone.fallback_recommended,
                        tronquee=zone.truncated,
                        jobs_replanifies=resolution.nb_jobs_affected,
                        horizon_zone=zone.search_horizon,
                        max_jobs=zone.max_impacted_jobs,
                        valide=not validate_schedule(resolution.schedule,
                                                     instance=instance),
                    )
                lignes.append(ligne)
    return {"densites": densites, "lignes": lignes}


def lignes_du_regime(donnees, regime) -> list:
    return [l for l in donnees["lignes"] if l["regime"] == regime]


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------
def _oui_non(valeur, gras_si_vrai=True):
    """Rendu d'un booleen. Le gras ne sert qu'a signaler ce qui merite attention."""
    if valeur is None:
        return "—"
    if not valeur:
        return "non"
    return "**oui**" if gras_si_vrai else "oui"


def _table_regime(donnees, regime) -> list:
    lignes = [
        "| Densité | Utilisation | Perturbation | Jobs zone | Jobs futurs | "
        "% futurs touchés | Zone tronquée | Repli déclenché | Jobs replanifiés | "
        "Planning valide |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for l in lignes_du_regime(donnees, regime):
        if l["erreur"]:
            lignes.append(
                f"| {l['densite']} | {l['utilisation_pct']} % | {l['perturbation']} | "
                f"— | — | — | — | — | — | échec : `{l['erreur']}` |"
            )
            continue
        lignes.append(
            f"| {l['densite']} | {l['utilisation_pct']} % | {l['perturbation']} | "
            f"{l['jobs_zone']} | {l['jobs_futurs']} | {l['pct_futurs']} % | "
            f"{_oui_non(l['tronquee'])} | {_oui_non(l['repli'])} | "
            f"{l['jobs_replanifies']} | {_oui_non(l['valide'], gras_si_vrai=False)} |"
        )
    return lignes


def rendu_markdown(donnees) -> str:
    lignes = [
        "# Densité du planning × perturbation — réordonnancement incrémental",
        "",
        "> Généré par `python -m tests.densite_report` (livrable 2 de la Discussion 2).",
        "> **Document exploratoire et descriptif** : il fournit les données factuelles",
        "> de la question produit restée ouverte, il ne la tranche pas.",
        "",
        "## Les trois variantes",
        "",
        "Obtenues en étirant le planning CP-SAT optimal d'un facteur `s` : toutes les",
        "dates de début (opérations et setups) sont multipliées par `s`, les durées",
        "restent inchangées, les deadlines suivent le même facteur. Voir",
        "`tests/densite_variants.py` pour la justification de ce levier — desserrer les",
        "deadlines ou raccourcir les durées ne change **pas** la densité sur cette",
        "instance, et réduire le nombre de jobs fausserait les pourcentages.",
        "",
        "| Densité | Facteur `s` | Horizon | Utilisation machine | Temps mort interne | Détail par machine | TWT | Jobs en retard |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for nom, m in donnees["densites"].items():
        detail = " ".join(
            f"{k}:{v}" for k, v in sorted(m["temps_mort_par_machine"].items())
        )
        lignes.append(
            f"| {nom} | {DENSITES[nom]} | {m['horizon']} | {m['utilisation_pct']} % | "
            f"{m['temps_mort']} | {detail} | {m['twt']:.2f} | {m['nb_jobs_late']}/10 |"
        )

    lignes += [
        "",
        "Le temps mort compté est **interne** — les trous entre deux occupations",
        "consécutives d'une machine. C'est lui, et lui seul, qui peut absorber un retard.",
        "Noter qu'en variante dense, la machine goulot M1 a **zéro** temps mort : elle est",
        "saturée, donc structurellement incapable d'absorber quoi que ce soit.",
        "",
        "## Protocole",
        "",
        f"Perturbations appliquées en valeur **absolue**, identiques d'une variante à",
        f"l'autre : panne de {DUREE_PANNE} unités sur la machine goulot, job urgent de",
        f"2 opérations, dépassement de durée ×{FACTEUR_DEPASSEMENT}. T_now = un tiers de",
        "l'horizon de la variante. C'est le cœur de la mesure : une panne de 20 unités",
        "reste une panne de 20 unités, que le planificateur se soit gardé de la marge ou",
        "non — la question posée est donc bien « cette marge absorbe-t-elle la",
        "perturbation ? ».",
        "",
        "Deux régimes de bornes sont mesurés séparément, et c'est **indispensable** pour",
        "lire les chiffres correctement.",
        "",
        "## Régime 1 — comportement de production (bornes relatives par défaut, cf. D7)",
        "",
        "Ce que fera réellement le worker : bornes à 0.15 de l'horizon restant et 0.20",
        "des jobs futurs.",
        "",
    ]
    lignes += _table_regime(donnees, "production")
    lignes += [
        "",
        "**Lecture — attention au piège.** Avec 8 à 9 jobs futurs, le plafond relatif de",
        "0.20 vaut 1 à 2 jobs. La zone est donc **tronquée par le plafond dans presque",
        "toutes les cellules**, quelle que soit la densité. Ce régime montre que",
        "l'incrémental reste borné et que le garde-fou ne se déclenche jamais — mais il",
        "ne dit **rien** sur l'effet de la densité, que le plafond masque entièrement.",
        "C'est le régime 2 qui répond à cette question.",
        "",
        "## Régime 2 — cascade naturelle (bornes relâchées)",
        "",
        "Bornes volontairement relevées (`search_horizon=10 000`,",
        "`max_impacted_jobs=50`) pour observer jusqu'où la perturbation se propage",
        "réellement. C'est cette propagation-là que la densité influence, et c'est elle",
        "qui détermine si le seuil de repli serait franchi sans plafond.",
        "",
    ]
    lignes += _table_regime(donnees, "cascade_naturelle")
    lignes += ["", "## Lecture", ""]
    lignes += _observations(donnees)
    lignes += [
        "",
        "## Ce que ce rapport ne dit pas",
        "",
        "Il ne tranche pas entre **conserver de la marge à l'optimisation initiale** et",
        "**relever le seuil de repli**. Les deux lectures restent ouvertes :",
        "",
        "- garder de la marge a un coût direct et chiffrable — l'horizon s'allonge et le",
        "  retard pondéré augmente, ce que la colonne TWT du premier tableau quantifie ;",
        "- relever le seuil ne coûte rien à l'optimisation initiale, mais fait tourner",
        "  l'incrémental sur des zones plus larges, là où une résolution complète serait",
        "  peut-être plus pertinente.",
        "",
        "Une troisième lecture apparaît dans les chiffres et mérite d'être posée : le",
        "plafond relatif de D7 borne déjà la zone bien avant que le seuil de repli n'entre",
        "en jeu. Sur cette instance, le garde-fou de repli ne se déclenche donc jamais en",
        "régime de production — ce qui interroge son rôle réel, sans que ce rapport",
        "tranche non plus cette question.",
        "",
        "Le choix appartient à Khalid.",
    ]
    return "\n".join(lignes) + "\n"


def _observations(donnees) -> list:
    """Constats factuels tires des chiffres, sans recommandation."""
    obs = []
    for regime in REGIMES:
        par_densite = {}
        for l in lignes_du_regime(donnees, regime):
            if l["erreur"] is None:
                par_densite.setdefault(l["densite"], []).append(l)
        obs.append(f"**Régime {regime}** :")
        obs.append("")
        for nom, lignes in par_densite.items():
            replis = sum(1 for l in lignes if l["repli"])
            tronquees = sum(1 for l in lignes if l["tronquee"])
            pcts = [l["pct_futurs"] for l in lignes]
            obs.append(
                f"- **{nom}** ({donnees['densites'][nom]['utilisation_pct']} % "
                f"d'utilisation) : part des jobs futurs touchés de {min(pcts)} % à "
                f"{max(pcts)} %, {replis} repli(s) et {tronquees} zone(s) tronquée(s) "
                f"sur {len(lignes)} perturbation(s)."
            )
        obs.append("")

    naturel = {}
    for l in lignes_du_regime(donnees, "cascade_naturelle"):
        if l["erreur"] is None:
            naturel.setdefault(l["densite"], []).append(l["pct_futurs"])
    if len(naturel) >= 2:
        noms = list(naturel)
        premier, dernier = noms[0], noms[-1]
        moy_d = sum(naturel[premier]) / len(naturel[premier])
        moy_r = sum(naturel[dernier]) / len(naturel[dernier])
        sens = "diminue" if moy_r < moy_d else ("augmente" if moy_r > moy_d else "ne change pas")
        obs.append(
            f"- En cascade naturelle, la part moyenne des jobs futurs touchés {sens} "
            f"entre la variante *{premier}* ({moy_d:.0f} %) et la variante "
            f"*{dernier}* ({moy_r:.0f} %)."
        )

    invalides = [l for l in donnees["lignes"] if l["valide"] is False]
    if invalides:
        obs.append(
            f"- ATTENTION : {len(invalides)} planning(s) fusionné(s) invalide(s) — "
            f"à investiguer."
        )
    else:
        obs.append(
            "- Tous les plannings fusionnés sont valides, dans les deux régimes et à "
            "toutes les densités : la cascade reste correcte y compris sur des zones "
            "larges non tronquées."
        )
    return obs


def rendu_console(donnees) -> None:
    print("=" * 92)
    print("DENSITE DU PLANNING x PERTURBATION")
    print("=" * 92)
    print()
    print(f"{'densite':10s} {'s':>4s} {'horizon':>8s} {'util':>7s} {'mort':>6s} "
          f"{'TWT':>10s} {'retard':>7s}")
    print("-" * 92)
    for nom, m in donnees["densites"].items():
        print(f"{nom:10s} {DENSITES[nom]:>4} {m['horizon']:>8d} "
              f"{m['utilisation_pct']:>6.1f}% {m['temps_mort']:>6d} "
              f"{m['twt']:>10.2f} {m['nb_jobs_late']:>5d}/10")

    for regime in REGIMES:
        print()
        print(f"--- REGIME : {regime} ---")
        print(f"{'densite':10s} {'perturbation':30s} {'zone':>7s} {'%fut':>6s} "
              f"{'tronq':>6s} {'repli':>6s} {'replan':>7s} {'valide':>7s}")
        print("-" * 92)
        for l in lignes_du_regime(donnees, regime):
            if l["erreur"]:
                print(f"{l['densite']:10s} {l['perturbation']:30s} "
                      f"ECHEC {l['erreur']}")
                continue
            print(f"{l['densite']:10s} {l['perturbation']:30s} "
                  f"{l['jobs_zone']:>3d}/{l['jobs_futurs']:<3d} {l['pct_futurs']:>5d}% "
                  f"{('OUI' if l['tronquee'] else 'non'):>6s} "
                  f"{('OUI' if l['repli'] else 'non'):>6s} "
                  f"{l['jobs_replanifies']:>7d} "
                  f"{('OK' if l['valide'] else 'NON'):>7s}")

    print()
    for ligne in _observations(donnees):
        if ligne:
            print("  " + ligne.replace("**", "").lstrip("- "))


def main() -> int:
    logging.disable(logging.WARNING)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass  # flux non reconfigurable (redirection, Python ancien) : sans gravite
    console_seule = "--console" in sys.argv

    donnees = collecte()
    rendu_console(donnees)

    if not console_seule:
        chemin = os.path.normpath(RAPPORT)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(rendu_markdown(donnees))
        print()
        print(f"Rapport ecrit dans {chemin}")

    invalides = [l for l in donnees["lignes"] if l["valide"] is False]
    return 1 if invalides else 0


if __name__ == "__main__":
    sys.exit(main())
