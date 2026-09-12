"""
Journalisation des perturbations reellement traitees.

Couche de SERVICE, volontairement distincte du coeur scheduling. Le sens de la
dependance est strict et ne doit pas s'inverser :

    app.perturbation_log  ──appelle──>  scheduling.resolve_incremental
                          ──ecrit──>    perturbation_events

`scheduling/incremental.py` n'importe aucun SQLAlchemy et ne doit jamais en importer
(cf. D9) : l'orchestrateur reste executable et testable sans base. C'est ce service qui
enchaine « resoudre puis journaliser », jamais l'orchestrateur qui appellerait une base.

## Pourquoi journaliser

Le socle sectoriel (`app/sectors.py`) repose sur des hypotheses qu'aucune donnee
marocaine ne valide. Ce journal produit la mesure qui les corrigera : pour un tenant
donne, quelle est sa VRAIE repartition de causes de replanification. Le secteur est un
point de depart, ces lignes sont la verite.
"""
from dataclasses import asdict, is_dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perturbation_event import PerturbationEventLog


def serialise_payload(payload) -> dict:
    """Rend un payload de perturbation stockable en JSON.

    Les payloads sont des dataclasses pouvant contenir des `Operation` (job urgent),
    elles-memes dataclasses : `asdict` les aplatit recursivement. Un payload qui ne
    serait pas une dataclass est refuse plutot que serialise approximativement — mieux
    vaut un echec franc qu'une ligne de journal inexploitable.
    """
    if not is_dataclass(payload):
        raise TypeError(
            f"payload de perturbation non serialisable : {type(payload).__name__}"
        )
    return asdict(payload)


async def journalise_evenement(
    session: AsyncSession,
    *,
    event,
    tenant_id,
    base_resolution_id,
    reported_by,
    triggered_resolution_id=None,
) -> PerturbationEventLog:
    """Ecrit une perturbation traitee dans le journal.

    Args:
        session: session SQLAlchemy asynchrone.
        event: le `PerturbationEvent` (dataclass du coeur scheduling).
        tenant_id: le tenant concerne.
        base_resolution_id: la resolution SUR laquelle porte la perturbation.
        reported_by: l'utilisateur qui la declare. Pour une origine automatisee
            (connecteur MES), utiliser un compte de service dedie — le champ reste
            non nul, conformement au schema de conception.
        triggered_resolution_id: la resolution DECLENCHEE, si elle existe deja.

    Returns:
        La ligne ajoutee a la session (non commitee : l'appelant maitrise sa
        transaction, ce qui lui permet d'ecrire resolution et evenement d'un bloc).
    """
    ligne = PerturbationEventLog(
        tenant_id=tenant_id,
        base_resolution_id=base_resolution_id,
        triggered_resolution_id=triggered_resolution_id,
        event_type=event.event_type.value,
        payload=serialise_payload(event.payload),
        reported_by=reported_by,
        event_timestamp=event.timestamp,
    )
    session.add(ligne)
    await session.flush()
    return ligne


async def resout_et_journalise(
    session: AsyncSession,
    *,
    schedule,
    event,
    instance,
    tenant_id,
    base_resolution_id,
    reported_by,
    t_now=None,
    config=None,
):
    """Deroule la cascade incrementale PUIS journalise l'evenement.

    C'est le seul endroit du projet ou resolution et persistance se rencontrent. Le
    coeur scheduling est appele tel quel, sans lui passer ni session ni identifiant :
    il ignore tout de la base, et doit continuer de l'ignorer.

    L'ecriture a lieu APRES une resolution reussie. Un evenement dont la resolution
    echoue n'est pas journalise : le journal recense ce qui a ete TRAITE, pas ce qui a
    ete tente. Journaliser les echecs est un besoin distinct, a trancher separement.

    Returns:
        (IncrementalResolution, PerturbationEventLog)
    """
    from scheduling.incremental import resolve_incremental

    resolution = resolve_incremental(
        schedule, event, instance, t_now=t_now, config=config
    )
    ligne = await journalise_evenement(
        session,
        event=event,
        tenant_id=tenant_id,
        base_resolution_id=base_resolution_id,
        reported_by=reported_by,
    )
    return resolution, ligne
