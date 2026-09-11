"""
Validation du signal de repli contre la matrice densite x perturbation (D13).

Le rapport lisible est `python -m tests.repli_report`. Ces tests verrouillent ses
proprietes QUALITATIVES — jamais les pourcentages exacts, qui dependent de la
solution CP-SAT initiale.

Ils repondent a la question de la session : le signal se declenche-t-il la ou la
cascade reelle le justifie, et **seulement** la ?
"""
import pytest

from tests.repli_report import collecte, rendu_markdown


@pytest.fixture(scope="module")
def lignes():
    """Les 9 cellules, collectees une seule fois (18 resolutions)."""
    return collecte()


def test_avant_d13_le_repli_ne_se_declenchait_jamais_en_production(lignes):
    """Le defaut, verrouille tel qu'il etait.

    La regle d'origine — ratio mesure > seuil — ne pouvait structurellement pas se
    declencher : le plafond de D7 (20 % des jobs futurs) est sous le seuil de H5
    (50 %). Ce test fige le constat pour que la comparaison AVANT / APRES reste
    verifiable, et non affirmee.
    """
    assert not any(l["production"]["repli_avant"] for l in lignes), (
        "aucune cellule ne pouvait declencher le repli avec la seule regle de ratio"
    )


def test_apres_d13_le_repli_se_declenche_sur_les_cascades_reellement_larges(lignes):
    """Le critere d'acceptation du livrable 3.

    Le signal doit se declencher exactement sur les cellules dont la cascade REELLE
    (mesuree bornes relachees) depasse le seuil de repli — alors meme que la zone
    mesuree en production reste tres en-dessous.
    """
    attendus = {
        (l["densite"], l["perturbation"]) for l in lignes
        if l["naturelle"]["pct"] / 100 > l["naturelle"]["seuil"]
    }
    obtenus = {
        (l["densite"], l["perturbation"]) for l in lignes if l["production"]["repli"]
    }

    assert obtenus == attendus, (
        f"faux negatifs : {sorted(attendus - obtenus)} ; "
        f"faux positifs : {sorted(obtenus - attendus)}"
    )
    assert attendus, "la matrice doit contenir au moins une cascade large"


def test_le_signal_reste_discriminant(lignes):
    """Un signal qui se declenche partout ne vaut pas mieux qu'un signal muet.

    C'est le risque qu'aurait fait courir l'inclusion de la coupe de precedence,
    qui se produit sur 8 cellules sur 9 : on aurait reproduit a l'envers le
    sur-declenchement que D7 avait ete cree pour corriger.
    """
    replis = [l for l in lignes if l["production"]["repli"]]
    assert 0 < len(replis) < len(lignes), (
        f"{len(replis)} cellule(s) sur {len(lignes)} declenchent le repli : "
        f"le signal doit discriminer, pas repondre toujours pareil"
    )


def test_la_troncature_seule_ne_suffit_pas_a_declencher(lignes):
    """`truncated` et `truncated_before_convergence` ne sont pas interchangeables.

    Les bornes de D7 tronquent presque partout ; seule une coupe sur propagation
    ACTIVE recommande le repli. Ce test verifie qu'il existe bien des cellules
    tronquees qui ne declenchent pas — sans quoi la distinction serait vide.
    """
    tronquees_sans_repli = [
        l for l in lignes
        if l["production"]["tronquee"] and not l["production"]["repli"]
    ]
    assert tronquees_sans_repli, (
        "aucune cellule tronquee sans repli : la distinction entre troncature et "
        "troncature active n'apporterait alors rien"
    )


def test_le_signal_ne_change_pas_la_zone_mesuree(lignes):
    """D13 est orthogonal a D7 : les bornes et la zone sont inchangees.

    Le correctif ajoute un signal, il ne modifie ni la taille de la zone ni la
    facon dont elle est bornee. La zone de production doit donc rester au plus
    aussi large que la cascade naturelle.
    """
    for l in lignes:
        assert l["production"]["jobs"] <= l["naturelle"]["jobs"], (
            f"{l['densite']} / {l['perturbation']} : la zone bornee depasse la "
            f"cascade naturelle"
        )


def test_le_rapport_markdown_se_genere(lignes):
    """Le livrable lisible se produit sans erreur et porte la comparaison."""
    texte = rendu_markdown(lignes)
    assert "# Validation du signal de repli" in texte
    assert "AVANT D13" in texte and "APRÈS D13" in texte
    assert "Cascade naturelle" in texte
