"""
PerturbationEvent : evenement declencheur d'un reordonnancement incremental.

Les 5 types couverts correspondent exactement aux valeurs de la contrainte CHECK
prevue pour la table `perturbation_events` (cf. docs/architecture-incremental.md
Sec. 2.7). Cette dataclass est une donnee pure : aucune dependance BDD ici, la
migration reelle est du ressort de la Discussion 4.

Chaque type d'evenement a son propre payload type. `payload` n'est donc jamais un
dict libre : c'est une des dataclasses `*Payload` ci-dessous, et l'association
type -> classe de payload est verifiee a la construction. La serialisation vers /
depuis la colonne `payload JSONB` passe par `to_dict()` / `from_dict()`, qui
figent le nommage des cles JSON.
"""
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

from scheduling.models.job import Operation


class PerturbationType(str, Enum):
    """Types d'evenement declencheur (miroir de la contrainte CHECK SQL)."""

    MACHINE_BREAKDOWN = "machine_breakdown"
    URGENT_JOB = "urgent_job"
    DURATION_CHANGE = "duration_change"
    JOB_CANCEL = "job_cancel"
    RESOURCE_CHANGE = "resource_change"


# --------------------------------------------------------------------------
# Payloads : un par type d'evenement
# --------------------------------------------------------------------------
@dataclass
class MachineBreakdownPayload:
    """M2 indisponible de start_time a end_time."""

    machine_id: str
    start_time: int
    end_time: int

    def __post_init__(self):
        if self.end_time <= self.start_time:
            raise ValueError(
                f"machine_breakdown: end_time ({self.end_time}) doit etre "
                f"strictement superieur a start_time ({self.start_time})"
            )

    @property
    def affected_entities(self) -> list:
        return [self.machine_id]


@dataclass
class UrgentJobPayload:
    """Nouvelle commande a inserer dans le planning existant.

    Les operations sont fournies telles quelles pour pouvoir construire le Job
    sans relire la BDD ; `position` est 1-indexe comme partout ailleurs.
    """

    job_id: str
    operations: list  # list[Operation]
    deadline: int
    weight: float

    def __post_init__(self):
        if not self.operations:
            raise ValueError("urgent_job: au moins une operation est requise")
        for op in self.operations:
            if not isinstance(op, Operation):
                raise TypeError(
                    f"urgent_job: operations doit contenir des Operation, recu {type(op).__name__}"
                )
            if op.job_id != self.job_id:
                raise ValueError(
                    f"urgent_job: operation rattachee a {op.job_id} au lieu de {self.job_id}"
                )
        if self.weight <= 0:
            raise ValueError(f"urgent_job: weight doit etre > 0, recu {self.weight}")

    @property
    def affected_entities(self) -> list:
        return [self.job_id]


@dataclass
class DurationChangePayload:
    """Une operation dure plus (ou moins) longtemps que prevu.

    L'operation est designee par (job_id, position_in_job), la meme cle que celle
    portee par ScheduleEntry ; `machine_id` est redondant mais conserve pour
    pouvoir recouper l'evenement sans relire l'instance.
    """

    job_id: str
    position_in_job: int
    machine_id: str
    new_duration: int

    def __post_init__(self):
        if self.position_in_job < 1:
            raise ValueError(
                f"duration_change: position_in_job est 1-indexe, recu {self.position_in_job}"
            )
        if self.new_duration <= 0:
            raise ValueError(
                f"duration_change: new_duration doit etre > 0, recu {self.new_duration}"
            )

    @property
    def affected_entities(self) -> list:
        return [self.job_id]


@dataclass
class JobCancelPayload:
    """Commande annulee : libere ses creneaux futurs."""

    job_id: str

    @property
    def affected_entities(self) -> list:
        return [self.job_id]


@dataclass
class ResourceChangePayload:
    """WR modifie temporairement (absence technicien) sur une fenetre.

    `new_wr` peut valoir 0 (plus aucun setup possible sur la periode).
    """

    new_wr: int
    start_time: int
    end_time: int

    def __post_init__(self):
        if self.new_wr < 0:
            raise ValueError(f"resource_change: new_wr doit etre >= 0, recu {self.new_wr}")
        if self.end_time <= self.start_time:
            raise ValueError(
                f"resource_change: end_time ({self.end_time}) doit etre "
                f"strictement superieur a start_time ({self.start_time})"
            )

    @property
    def affected_entities(self) -> list:
        return []


PAYLOAD_BY_TYPE = {
    PerturbationType.MACHINE_BREAKDOWN: MachineBreakdownPayload,
    PerturbationType.URGENT_JOB: UrgentJobPayload,
    PerturbationType.DURATION_CHANGE: DurationChangePayload,
    PerturbationType.JOB_CANCEL: JobCancelPayload,
    PerturbationType.RESOURCE_CHANGE: ResourceChangePayload,
}


@dataclass
class PerturbationEvent:
    """Evenement declencheur d'un re-solve incremental.

    - `event_type` : un des 5 types ; une valeur inconnue leve ValueError.
    - `timestamp`  : T_now, l'instant present, dans la meme unite entiere que les
      start_time / end_time des ScheduleEntry (pas un datetime).
    - `payload`    : la dataclass de payload correspondant au type.
    - `affected_entities` : deduit du payload si non fourni.
    """

    event_type: PerturbationType
    timestamp: int
    payload: object
    affected_entities: list = field(default_factory=list)

    def __post_init__(self):
        # Accepte aussi bien l'enum que la chaine brute venue de la BDD.
        try:
            self.event_type = PerturbationType(self.event_type)
        except ValueError:
            valides = ", ".join(t.value for t in PerturbationType)
            raise ValueError(
                f"Type de perturbation inconnu : {self.event_type!r}. Valides : {valides}"
            ) from None

        attendu = PAYLOAD_BY_TYPE[self.event_type]
        if not isinstance(self.payload, attendu):
            raise TypeError(
                f"payload de type {self.event_type.value} doit etre un "
                f"{attendu.__name__}, recu {type(self.payload).__name__}"
            )

        if self.timestamp < 0:
            raise ValueError(f"timestamp (T_now) doit etre >= 0, recu {self.timestamp}")

        if not self.affected_entities:
            self.affected_entities = list(self.payload.affected_entities)

    # -- serialisation vers / depuis la colonne `payload JSONB` --------------
    def to_dict(self) -> dict:
        """Forme serialisable ; `payload` correspond a la colonne JSONB."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "affected_entities": list(self.affected_entities),
            "payload": _payload_to_dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PerturbationEvent":
        """Reconstruit l'evenement depuis sa forme JSON (round-trip de to_dict)."""
        try:
            event_type = PerturbationType(data["event_type"])
        except ValueError:
            valides = ", ".join(t.value for t in PerturbationType)
            raise ValueError(
                f"Type de perturbation inconnu : {data['event_type']!r}. Valides : {valides}"
            ) from None

        payload_cls = PAYLOAD_BY_TYPE[event_type]
        raw = dict(data["payload"])
        if payload_cls is UrgentJobPayload:
            raw["operations"] = [Operation(**op) for op in raw["operations"]]
        return cls(
            event_type=event_type,
            timestamp=data["timestamp"],
            payload=payload_cls(**raw),
            affected_entities=list(data.get("affected_entities") or []),
        )


def _payload_to_dict(payload: object) -> dict:
    """asdict() gere les Operation imbriquees des payloads urgent_job."""
    return asdict(payload)


def make_event(
    event_type,
    timestamp: int,
    affected_entities: Optional[list] = None,
    **payload_fields,
) -> PerturbationEvent:
    """Raccourci de construction : les champs du payload sont passes a plat.

    Exemple :
        make_event("machine_breakdown", timestamp=100,
                   machine_id="M2", start_time=120, end_time=180)
    """
    try:
        resolved = PerturbationType(event_type)
    except ValueError:
        valides = ", ".join(t.value for t in PerturbationType)
        raise ValueError(
            f"Type de perturbation inconnu : {event_type!r}. Valides : {valides}"
        ) from None
    return PerturbationEvent(
        event_type=resolved,
        timestamp=timestamp,
        payload=PAYLOAD_BY_TYPE[resolved](**payload_fields),
        affected_entities=list(affected_entities or []),
    )
