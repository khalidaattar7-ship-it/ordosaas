"""
Revalidation de la matrice apres D14 — proprietes verrouillees.

Le rapport lisible est `python -m tests.absorption_report`. Ces tests verrouillent ses
constats QUALITATIVES, jamais les pourcentages exacts.
"""
import pytest

from tests.absorption_report import collecte, rendu_markdown
from tests.densite_variants import DENSITES


@pytest.fixture(scope="module")
def lignes():
    """Les 9 cellules en cascade naturelle, collectees une seule fois."""
    return collecte()


def test_labsorption_ne_peut_que_reduire_la_cascade(lignes):
    """Propriete structurelle : arreter plus tot ne peut pas elargir.

    L'absorption interrompt la propagation quand le retard est epuise ; elle ne
    marque donc jamais une operation que l'ancienne version aurait epargnee. Une
    cellule en hausse signalerait un defaut d'implementation, pas un effet de mesure.
    """
    hausses = [
        (l["densite"], l["perturbation"], l["avant"], l["apres"])
        for l in lignes if l["apres"] > l["avant"]
    ]
    assert hausses == [], f"cascades elargies par l'absorption : {hausses}"


def test_leffet_se_concentre_sur_la_densite_intermediaire(lignes):
    """Constat central de la revalidation.

    Le planning dense n'a pas de temps mort a absorber, et le detendu convergeait
    deja avant D14 par la seule contention. C'est donc la variante MODEREE qui bouge
    — celle qui a du temps mort, mais dont la precedence sur-propageait faute de le
    prendre en compte.
    """
    changees = {l["densite"] for l in lignes if l["avant"] != l["apres"]}
    assert changees == {"moderee"}, (
        f"l'effet devrait se concentrer sur la densite intermediaire, obtenu {changees}"
    )


def test_les_conclusions_qualitatives_tiennent(lignes):
    """Les trois conclusions de la Discussion 2, revérifiees et non supposees."""
    def pct(densite, fragment):
        for l in lignes:
            if l["densite"] == densite and fragment in l["perturbation"]:
                return l["apres"]
        raise KeyError((densite, fragment))

    # 1. La marge aide sur les aleas subis.
    assert pct("dense", "panne") > pct("moderee", "panne")
    assert pct("dense", "depassement") > pct("moderee", "depassement")

    # 2. La marge n'aide pas sur les insertions : le planning sature reste le
    #    meilleur cas pour un job urgent.
    urgents = {d: pct(d, "urgent") for d in DENSITES}
    assert urgents["dense"] <= min(urgents.values())

    # 3. Le repli ne se declenche que sur le planning dense.
    replis = {l["densite"] for l in lignes if l["repli"]}
    assert replis == {"dense"}


def test_moderee_et_detendue_deviennent_indiscernables(lignes):
    """La nuance NOUVELLE apportee par D14, verrouillee telle qu'observee.

    Une fois qu'un planning comporte assez de marge pour que la cascade converge
    d'elle-meme, en ajouter davantage ne change plus rien : l'effet de la densite
    n'est pas graduel, il y a un seuil. Le cout de la marge, lui, continue de
    croitre — information utile pour l'arbitrage produit encore ouvert.
    """
    par_densite = {}
    for l in lignes:
        par_densite.setdefault(l["densite"], {})[l["perturbation"]] = l["apres"]

    assert par_densite["moderee"] == par_densite["detendue"], (
        "les deux variantes aerees devraient donner des cascades identiques"
    )
    assert par_densite["dense"] != par_densite["moderee"], (
        "le planning sature doit rester distinct"
    )


def test_le_rapport_markdown_se_genere(lignes):
    texte = rendu_markdown(lignes)
    assert "# Revalidation de la matrice" in texte
    assert "Avant D14" in texte and "Après D14" in texte
    assert "Les conclusions qualitatives tiennent-elles ?" in texte
