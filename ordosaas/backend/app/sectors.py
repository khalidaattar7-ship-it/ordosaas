"""
Socle de configuration par secteur d'activite.

Cette couche PROPOSE des valeurs de depart, elle n'en applique aucune. Le nom des
fonctions le dit : `defauts_pour_secteur()` retourne un dictionnaire, sans ecrire nulle
part et sans effet de bord. C'est l'appelant — l'API de la Discussion 4 — qui decidera
quand et comment s'en servir, avec ou sans possibilite de surcharge.

## Pourquoi une proposition et jamais une application

Deux raisons, dont une structurelle :

1. `SolverConfig` exige un `instance_id`. Une configuration ne peut donc PAS exister au
   moment ou le tenant est cree — il n'y a pas encore d'instance. « Appliquer le socle a
   l'inscription » est impossible par construction, pas seulement discutable.
2. `Tenant` porte deja `default_wr`, `default_timeout` et `default_strategy`, qui
   existent precisement pour etre fixes librement par l'utilisateur. Les ecraser avec
   une hypothese sectorielle non validee reviendrait a imposer ce qui doit rester une
   suggestion.

## Ces valeurs sont des hypotheses, pas des faits

Elles proviennent d'indices STRUCTURELS sur les secteurs industriels marocains, sans
aucune donnee quantifiee a l'appui — c'est reconnu et assume. Elles vivent en base
(table `sector_defaults`) et non en constantes Python, pour qu'un ajustement soit un
UPDATE et non un deploiement.

C'est aussi la raison d'etre de `app.perturbation_stats` : une fois que des evenements
reels seront journalises, la repartition observee des causes de replanification dira ce
que ces hypotheses valaient. Le secteur est un point de depart, les logs sont la verite.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sector_default import SECTEUR_PAR_DEFAUT, SECTEURS, SectorDefault

#: Reglages proposes quand aucune ligne sectorielle n'existe en base. Ce sont les
#: defauts actuels du projet, ceux de `SolverConfig` — donc aucune supposition.
SOCLE_NEUTRE = {
    "wr": 5,
    "stability_weight": 0.1,
    "cpsat_timeout": 30,
    "strategy": "auto",
}


#: Socle initial, source Python de reference. La migration 0004 seme les memes lignes
#: en SQL : une migration doit rester SELF-CONTAINED (figee dans le temps), elle
#: n'importe donc pas ce module. Cette duplication est DELIBEREE et limitee au
#: peuplement initial ; la verite d'execution reste la table, modifiable par UPDATE.
SOCLE_INITIAL = {
    "cablage_auto": {
        "wr": 5, "stability_weight": 0.3, "cpsat_timeout": 30, "strategy": "auto",
        "rationale": (
            "HYPOTHESE non validee : flux JIS, insertions urgentes frequentes. Un poids "
            "de stabilite releve (0.3 au lieu de 0.1) vise a limiter le bouleversement "
            "du planning a chaque insertion. Aucune donnee marocaine quantifiee."
        ),
    },
    "textile": {
        "wr": 5, "stability_weight": 0.3, "cpsat_timeout": 30, "strategy": "auto",
        "rationale": (
            "HYPOTHESE non validee : fast-fashion, reordonnancements frequents sur "
            "commande. Meme raisonnement que le cablage automobile."
        ),
    },
    "plasturgie": {
        "wr": 8, "stability_weight": 0.1, "cpsat_timeout": 30, "strategy": "auto",
        "rationale": (
            "HYPOTHESE non validee : aleas subis dominants (pannes courtes frequentes, "
            "changements de serie longs). Davantage de techniciens setup pour absorber "
            "les changements."
        ),
    },
    "sous_traitance_mecanique": {
        "wr": 6, "stability_weight": 0.1, "cpsat_timeout": 30, "strategy": "auto",
        "rationale": (
            "HYPOTHESE non validee : profil mixte penchant vers les aleas subis, moins "
            "marque que la plasturgie."
        ),
    },
    "agro_alimentaire": {
        "wr": 5, "stability_weight": 0.1, "cpsat_timeout": 30, "strategy": "auto",
        "rationale": (
            "Profil mixte sans signal net : defauts actuels du projet conserves. Aucune "
            "supposition."
        ),
    },
    "autre": {
        "wr": 5, "stability_weight": 0.1, "cpsat_timeout": 30, "strategy": "auto",
        "rationale": "Secteur par defaut. Defauts actuels du projet, aucune supposition.",
    },
}


async def seme_le_socle(session: AsyncSession) -> int:
    """Insere les lignes manquantes du socle initial. Idempotent.

    Destine aux tests et a l'amorcage programmatique d'une base creee par
    `Base.metadata.create_all` — la production, elle, est semee par la migration 0004.
    Ne MODIFIE jamais une ligne existante : une valeur ajustee en base ne doit pas
    etre ecrasee par un reamorcage.
    """
    existants = set((await tous_les_defauts(session)).keys())
    ajoutes = 0
    for secteur, valeurs in SOCLE_INITIAL.items():
        if secteur in existants:
            continue
        session.add(SectorDefault(sector=secteur, **valeurs))
        ajoutes += 1
    await session.flush()
    return ajoutes


class SecteurInconnuError(ValueError):
    """Le secteur demande ne fait pas partie de la taxonomie."""

    def __init__(self, secteur):
        self.secteur = secteur
        super().__init__(
            f"Secteur inconnu : {secteur!r}. Valides : {', '.join(SECTEURS)}."
        )


async def defauts_pour_secteur(session: AsyncSession, secteur: str) -> dict:
    """Reglages PROPOSES pour un secteur. N'ecrit rien, ne decide rien.

    Args:
        session: session SQLAlchemy asynchrone.
        secteur: l'un des `SECTEURS`.

    Returns:
        Un dictionnaire de reglages — `wr`, `stability_weight`, `cpsat_timeout`,
        `strategy` — plus `secteur` et `rationale` pour que l'appelant puisse
        expliquer d'ou viennent ces valeurs.

        Si aucune ligne n'existe pour ce secteur, renvoie le socle neutre : les
        defauts actuels du projet. Une table vide degrade donc vers le comportement
        d'aujourd'hui, jamais vers une erreur.

    Raises:
        SecteurInconnuError: si le secteur n'appartient pas a la taxonomie. On ne
            degrade PAS silencieusement vers `autre` : une valeur hors taxonomie
            revele un defaut d'appelant, et le masquer le rendrait indetectable.
    """
    if secteur not in SECTEURS:
        raise SecteurInconnuError(secteur)

    ligne = await session.get(SectorDefault, secteur)
    if ligne is None:
        return {"secteur": secteur, "rationale": None, **SOCLE_NEUTRE}

    return {
        "secteur": ligne.sector,
        "wr": ligne.wr,
        "stability_weight": float(ligne.stability_weight),
        "cpsat_timeout": ligne.cpsat_timeout,
        "strategy": ligne.strategy,
        "rationale": ligne.rationale,
    }


async def defauts_pour_tenant(session: AsyncSession, tenant) -> dict:
    """Raccourci : les reglages proposes pour le secteur d'un tenant.

    Un tenant dont le secteur serait absent (donnee ancienne) est traite comme
    `autre`, ce qui ne suppose rien.
    """
    return await defauts_pour_secteur(session, tenant.sector or SECTEUR_PAR_DEFAUT)


async def tous_les_defauts(session: AsyncSession) -> dict:
    """Le socle complet, secteur par secteur. Utile a l'inspection et aux tests."""
    lignes = (await session.execute(select(SectorDefault))).scalars().all()
    return {l.sector: l for l in lignes}
