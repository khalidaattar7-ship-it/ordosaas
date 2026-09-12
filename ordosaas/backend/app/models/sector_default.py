"""SectorDefault ORM model — socle de configuration par secteur d'activite.

Table de REFERENCE, pas de configuration active : elle porte, pour chaque secteur,
les valeurs de depart proposees a un nouveau tenant. Rien ne les applique
automatiquement — `app.sectors.defauts_pour_secteur()` les PROPOSE, l'appelant decide.

Elle vit en base, et non en constantes Python, pour une raison precise : ces valeurs
sont des HYPOTHESES non validees empiriquement (cf. la section dediee de
docs/CONTEXTE_ET_DECISIONS.md), destinees a etre revisees des que des donnees reelles
existeront. Les ajuster doit donc etre un UPDATE, pas un deploiement.

La cle primaire est le secteur lui-meme : une ligne par secteur, garantie par le
schema. C'est le seul modele du projet a ne pas porter d'`id` UUID, precisement parce
qu'il s'agit d'une table de reference a cardinalite fermee.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: Taxonomie fermee des secteurs. `autre` est le defaut et ne suppose rien.
SECTEURS = (
    "cablage_auto",
    "plasturgie",
    "agro_alimentaire",
    "textile",
    "sous_traitance_mecanique",
    "autre",
)

SECTEUR_PAR_DEFAUT = "autre"

#: Fragment SQL partage entre les CheckConstraint des deux tables concernees.
CONTRAINTE_SECTEUR = "IN (" + ", ".join(f"'{s}'" for s in SECTEURS) + ")"


class SectorDefault(Base):
    """Valeurs de configuration proposees pour un secteur donne."""

    __tablename__ = "sector_defaults"
    __table_args__ = (
        CheckConstraint(f"sector {CONTRAINTE_SECTEUR}", name="ck_sector_defaults_sector"),
        CheckConstraint("wr BETWEEN 1 AND 50", name="ck_sector_defaults_wr"),
        CheckConstraint("stability_weight >= 0", name="ck_sector_defaults_stability"),
        CheckConstraint(
            "cpsat_timeout BETWEEN 5 AND 300", name="ck_sector_defaults_timeout"
        ),
        CheckConstraint(
            "strategy IN ('auto','cpsat','lns','atcs')", name="ck_sector_defaults_strategy"
        ),
    )

    sector: Mapped[str] = mapped_column(String(30), primary_key=True)
    wr: Mapped[int] = mapped_column(Integer, nullable=False)
    stability_weight: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    cpsat_timeout: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Pourquoi ces valeurs, et sur quelle base — indispensable puisqu'elles sont
    #: des hypotheses revisables et non des conclusions.
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=func.now(),
        onupdate=func.now(),
    )
