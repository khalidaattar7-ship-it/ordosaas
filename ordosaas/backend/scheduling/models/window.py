"""Time window dataclass used by the windowed solvers."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Window:
    index: int
    t_start: int
    t_end: int
    job_ids: list = field(default_factory=list)
    status: str = "pending"
    method_used: str | None = None
    recursion_depth: int = 0
    local_weighted_tardiness: float | None = None

    @property
    def nb_jobs(self) -> int:
        return len(self.job_ids)
