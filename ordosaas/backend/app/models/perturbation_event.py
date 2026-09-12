"""PerturbationEvent ORM model — journal des causes de replanification.

Contrepartie persistee de la dataclass `scheduling.models.perturbation.PerturbationEvent`
(decision D5 : donnee pure, sans dependance base). Les deux coexistent volontairement :

- la **dataclass** circule dans le coeur scheduling, qui doit rester executable et
  testable sans base (cf. D9) ;
- le **modele ORM** journalise ce qui a reellement ete traite, pour qu'on puisse dire
  plus tard, chiffres a l'appui, ce qui provoque vraiment les replanifications chez un
  tenant donne.

C'est le filet de securite du socle sectoriel : ce dernier repose sur des hypotheses non
validees, ce journal produira la verite qui les corrige.

## Contraintes de cle etrangere

`base_resolution_id` et `reported_by` sont NON NULS, conformement au schema de
conception. Un evenement d'origine automatisee — futur connecteur MES — sera attribue a
un COMPTE DE SERVICE dedie dans `users`, pas a un champ nul : aucune migration de schema
ne sera necessaire pour ce cas.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._types import JSONB, UUID

#: Les cinq types, alignes sur `scheduling.models.perturbation.PerturbationType`.
#: La coherence entre les deux est verrouillee par un test.
TYPES_EVENEMENT = (
    "machine_breakdown",
    "urgent_job",
    "duration_change",
    "job_cancel",
    "resource_change",
)

CONTRAINTE_TYPE = "IN (" + ", ".join(f"'{t}'" for t in TYPES_EVENEMENT) + ")"


class PerturbationEventLog(Base):
    """Une perturbation reellement traitee, journalisee.

    Le suffixe `Log` distingue sans ambiguite ce modele de la dataclass du coeur
    scheduling, qui porte deja le nom `PerturbationEvent`.
    """

    __tablename__ = "perturbation_events"
    __table_args__ = (
        CheckConstraint(f"event_type {CONTRAINTE_TYPE}", name="ck_perturbation_type"),
        Index("idx_perturbation_tenant", "tenant_id"),
        Index("idx_perturbation_type", "event_type"),
        Index("idx_perturbation_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    #: La resolution SUR laquelle porte la perturbation.
    base_resolution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resolutions.id"), nullable=False
    )
    #: La resolution que la perturbation a DECLENCHEE, si elle a abouti. Nulle tant que
    #: le traitement n'a rien produit — un evenement refuse par le garde-fou de repli,
    #: par exemple, reste journalise sans resolution declenchee.
    triggered_resolution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resolutions.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Le payload type de la dataclass, serialise. Conserve integralement : c'est lui
    #: qui permettra de rejouer ou d'auditer un evenement passe.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reported_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    #: Instant present de la perturbation, au sens du planning (T_now), a ne pas
    #: confondre avec `created_at`, qui est l'instant d'ecriture en base.
    event_timestamp: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now(),
        nullable=False,
    )
