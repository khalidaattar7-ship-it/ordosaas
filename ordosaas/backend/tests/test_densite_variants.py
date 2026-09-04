"""
Tests des variantes de densite et du rapport densite x perturbation.

Livrable 2 de la Discussion 2. Ces tests verrouillent les proprietes QUALITATIVES
du levier d'etirement et les constats structurels du rapport — jamais les chiffres
exacts, qui dependent de la solution CP-SAT initiale et n'ont pas a etre figes.

Le rapport lui-meme (`python -m tests.densite_report`) reste le livrable lisible :
ces tests garantissent seulement qu'il mesure ce qu'il pretend mesurer.
"""
import pytest

from scheduling.validation import validate_schedule
from tests.densite_report import collecte, lignes_du_regime, rendu_markdown
from tests.densite_variants import (
    DENSITES,
    charge_instance_exemple,
    construit_variantes,
    etire,
    mesure_densite,
)


@pytest.fixture(scope="module")
def variantes():
    """Les trois variantes, construites une seule fois pour tout le module."""
    return construit_variantes()


@pytest.fixture(scope="module")
def rapport():
    """La matrice complete, collectee une seule fois (18 resolutions)."""
    return collecte()


# -- le levier d'etirement ---------------------------------------------------
def test_letirement_preserve_la_validite(variantes):
    """Propriete demontree dans la docstring du module, verifiee ici en pratique."""
    for nom, (schedule, instance) in variantes.items():
        assert validate_schedule(schedule, instance=instance) == [], (
            f"la variante {nom} produit un planning invalide"
        )


def test_letirement_conserve_les_dix_jobs(variantes):
    """Pas de biais de denominateur : les variantes restent comparables entre elles.

    C'est la raison pour laquelle l'etirement a ete prefere a la reduction du nombre
    de jobs, qui aere aussi le planning mais change le denominateur du ratio sur
    lequel porte le garde-fou.
    """
    for nom, (schedule, instance) in variantes.items():
        assert len(instance.jobs) == 10, f"variante {nom}"
        assert len({e.job_id for e in schedule.entries}) == 10, f"variante {nom}"


def test_letirement_conserve_les_durees_et_lordre(variantes):
    """Seules les dates bougent : ni les durees ni la sequence machine ne changent."""
    dense, _ = variantes["dense"]
    detendue, _ = variantes["detendue"]

    durees_dense = {(e.job_id, e.position_in_job): e.duration for e in dense.entries}
    durees_detendue = {
        (e.job_id, e.position_in_job): e.duration for e in detendue.entries
    }
    assert durees_dense == durees_detendue

    def sequence(schedule, machine_id):
        return [
            e.job_id for e in sorted(
                (e for e in schedule.entries if e.machine_id == machine_id),
                key=lambda e: e.start_time,
            )
        ]

    for machine_id in {e.machine_id for e in dense.entries}:
        assert sequence(dense, machine_id) == sequence(detendue, machine_id)


def test_la_densite_decroit_avec_le_facteur(variantes):
    """Le levier fait bien ce qu'on attend de lui, dans le bon sens."""
    mesures = {
        nom: mesure_densite(schedule, instance)
        for nom, (schedule, instance) in variantes.items()
    }
    utilisations = [mesures[nom]["utilisation_pct"] for nom in DENSITES]
    temps_morts = [mesures[nom]["temps_mort"] for nom in DENSITES]

    assert utilisations == sorted(utilisations, reverse=True), (
        f"l'utilisation devrait decroitre de dense a detendue, obtenu {utilisations}"
    )
    assert temps_morts == sorted(temps_morts), (
        f"le temps mort devrait croitre de dense a detendue, obtenu {temps_morts}"
    )


def test_la_machine_goulot_est_saturee_en_variante_dense(variantes):
    """Constat structurel a l'origine de tout le sujet.

    En variante dense, au moins une machine n'a AUCUN temps mort interne : elle ne
    peut structurellement rien absorber. C'est ce qui explique que la cascade y soit
    si large, et c'est precisement ce que la marge corrige.
    """
    schedule, instance = variantes["dense"]
    mesures = mesure_densite(schedule, instance)
    assert 0 in mesures["temps_mort_par_machine"].values()

    schedule, instance = variantes["detendue"]
    mesures = mesure_densite(schedule, instance)
    assert all(v > 0 for v in mesures["temps_mort_par_machine"].values()), (
        "en variante detendue, toutes les machines devraient avoir du temps mort"
    )


def test_un_facteur_inferieur_a_un_est_refuse():
    """Comprimer le planning n'a pas de sens et casserait la preuve de validite."""
    instance = charge_instance_exemple()
    with pytest.raises(ValueError, match="facteur"):
        etire(None, instance, 0.5)


# -- le rapport --------------------------------------------------------------
def test_la_cascade_naturelle_se_reduit_quand_la_densite_baisse(rapport):
    """LE constat du livrable 2, verrouille.

    A perturbation identique en valeur absolue, la part des jobs futurs touchee par
    la cascade diminue nettement quand le planning est plus aere. C'est la donnee
    factuelle de la question produit.
    """
    par_densite = {}
    for ligne in lignes_du_regime(rapport, "cascade_naturelle"):
        if ligne["erreur"] is None:
            par_densite.setdefault(ligne["densite"], []).append(ligne["pct_futurs"])

    moyennes = {
        nom: sum(v) / len(v) for nom, v in par_densite.items()
    }
    assert moyennes["dense"] > moyennes["moderee"] > moyennes["detendue"], (
        f"la cascade devrait se reduire avec la densite, obtenu {moyennes}"
    )


def test_le_repli_ne_se_declenche_que_sur_le_planning_dense(rapport):
    """Le garde-fou distingue bien les deux situations, en cascade naturelle."""
    replis = {
        ligne["densite"]
        for ligne in lignes_du_regime(rapport, "cascade_naturelle")
        if ligne["repli"]
    }
    assert "detendue" not in replis, (
        "un planning aere ne devrait pas declencher le repli"
    )
    assert replis <= {"dense"}, (
        f"seul le planning dense devrait declencher le repli, obtenu {replis}"
    )


def test_en_production_le_plafond_relatif_borne_avant_le_garde_fou(rapport):
    """Constat important pour la lecture du rapport, et pour la Discussion 3.

    Avec les bornes relatives par defaut (D7), le plafond tronque la zone bien avant
    que le seuil de repli n'entre en jeu : sur cette instance le garde-fou ne se
    declenche jamais en regime de production. Ce test rend ce constat explicite au
    lieu de le laisser deduire du tableau.
    """
    lignes = [l for l in lignes_du_regime(rapport, "production") if l["erreur"] is None]
    assert lignes, "le regime de production n'a produit aucune ligne"
    assert not any(l["repli"] for l in lignes)
    assert any(l["tronquee"] for l in lignes)


def test_tous_les_plannings_fusionnes_sont_valides(rapport):
    """Critere transverse : la cascade reste correcte partout, densite comprise."""
    invalides = [
        (l["regime"], l["densite"], l["perturbation"])
        for l in rapport["lignes"] if l["valide"] is False
    ]
    assert invalides == [], f"plannings fusionnes invalides : {invalides}"


def test_aucune_cellule_de_la_matrice_nechoue(rapport):
    """Les 18 cellules doivent produire un resultat, pas une exception."""
    echecs = [
        (l["regime"], l["densite"], l["perturbation"], l["erreur"])
        for l in rapport["lignes"] if l["erreur"] is not None
    ]
    assert echecs == [], f"cellules en echec : {echecs}"
    assert len(rapport["lignes"]) == 18, "3 densites x 3 perturbations x 2 regimes"


def test_le_rapport_markdown_se_genere(rapport):
    """Le livrable lisible se produit sans erreur et contient les deux regimes."""
    texte = rendu_markdown(rapport)
    assert "# Densité du planning × perturbation" in texte
    assert "Régime 1 — comportement de production" in texte
    assert "Régime 2 — cascade naturelle" in texte
    assert "Le choix appartient à Khalid." in texte
    for nom in DENSITES:
        assert nom in texte
