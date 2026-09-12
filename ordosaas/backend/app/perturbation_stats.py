"""
Repartition reelle des causes de replanification, par tenant.

C'est la MESURE, pas la boucle d'ajustement. Cette fonction dit ce qui provoque
reellement les replanifications chez un tenant ; decider si et comment recalibrer son
socle sectoriel a partir de ce constat est une decision distincte, a prendre une fois
qu'on aura vu a quoi ressemblent de vraies donnees.

Aucun endpoint ici : la Discussion 4 exposera cette couche, elle n'aura pas a la
concevoir.
"""
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perturbation_event import TYPES_EVENEMENT, PerturbationEventLog


@dataclass
class RepartitionCauses:
    """Ce que le journal dit des causes de replanification d'un tenant."""

    tenant_id: object
    total: int
    #: {event_type: nombre}, les cinq types toujours presents, a zero si absents.
    comptes: dict = field(default_factory=dict)
    #: {event_type: pourcentage arrondi a 0.1}, vide si aucun evenement.
    pourcentages: dict = field(default_factory=dict)
    depuis: object = None
    jusqua: object = None

    @property
    def sans_historique(self) -> bool:
        """Aucun evenement sur la fenetre : le constat est vide, pas errone."""
        return self.total == 0

    @property
    def cause_dominante(self):
        """Le type le plus frequent, ou None sans historique.

        En cas d'egalite parfaite, renvoie le premier dans l'ordre de
        `TYPES_EVENEMENT` — arbitraire mais deterministe, ce qui vaut mieux qu'un
        resultat dependant de l'ordre de la base.
        """
        if self.sans_historique:
            return None
        maximum = max(self.comptes.values())
        return next(t for t in TYPES_EVENEMENT if self.comptes[t] == maximum)


async def repartition_des_causes(
    session: AsyncSession,
    tenant_id,
    depuis=None,
    jusqua=None,
) -> RepartitionCauses:
    """Repartition des types de perturbation pour un tenant, sur une fenetre.

    Args:
        session: session SQLAlchemy asynchrone.
        tenant_id: le tenant analyse.
        depuis: borne INCLUSIVE de debut (datetime), ou None pour tout l'historique.
        jusqua: borne EXCLUSIVE de fin (datetime), ou None.

    Returns:
        Un `RepartitionCauses`. **Les cinq types sont toujours presents** dans
        `comptes`, a zero si absents : un appelant qui trace un graphique n'a pas a
        gerer des cles manquantes, et l'absence d'un type est une information en soi.

        Sans aucun evenement, `total` vaut 0, `pourcentages` est VIDE et
        `sans_historique` est vrai — jamais de division par zero silencieuse, jamais
        d'erreur non plus : un tenant qui n'a rien replanifie est un cas normal.

    La fenetre porte sur `created_at`, l'instant d'ECRITURE, et non sur
    `event_timestamp`, qui est un temps de planning sans origine commune entre
    resolutions et n'est donc pas comparable d'une instance a l'autre.
    """
    requete = (
        select(PerturbationEventLog.event_type, func.count())
        .where(PerturbationEventLog.tenant_id == tenant_id)
        .group_by(PerturbationEventLog.event_type)
    )
    if depuis is not None:
        requete = requete.where(PerturbationEventLog.created_at >= depuis)
    if jusqua is not None:
        requete = requete.where(PerturbationEventLog.created_at < jusqua)

    bruts = dict((await session.execute(requete)).all())
    comptes = {t: int(bruts.get(t, 0)) for t in TYPES_EVENEMENT}
    total = sum(comptes.values())

    pourcentages = (
        {t: round(100 * n / total, 1) for t, n in comptes.items()} if total else {}
    )
    return RepartitionCauses(
        tenant_id=tenant_id, total=total, comptes=comptes,
        pourcentages=pourcentages, depuis=depuis, jusqua=jusqua,
    )
