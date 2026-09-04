"""Window and WindowResult models for the windowed LNS solver."""
from dataclasses import dataclass, field

from scheduling.models.context import BoundaryContext
from scheduling.models.schedule import Schedule


@dataclass
class Window:
    index: int  # 1-indexed
    t_start: int
    t_end: int
    jobs: list  # list[Job]

    @property
    def nb_jobs(self) -> int:
        return len(self.jobs)


@dataclass
class WindowResult:
    window: Window
    schedule: Schedule
    exit_context: BoundaryContext
    objective: float
    method: str  # 'optimal', 'feasible', 'atcs_fallback', ...
    duration_seconds: float = 0.0
    recursion_depth: int = 0
    # Setups de jonction vers le futur non touche, produits par IncrementalOptimizer
    # (cf. D8) : {(job_id, position_in_job) de l'entree non touchee -> SetupEntry}.
    # Vide pour le LNS initial, qui n'a pas de jonction de ce type.
    junction_setups: dict = field(default_factory=dict)
