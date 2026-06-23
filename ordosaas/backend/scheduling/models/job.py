"""Scheduling domain dataclasses for jobs and operations."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Operation:
    op_id: str
    machine_id: str
    duration: int
    position: int


@dataclass
class Job:
    job_id: str
    deadline: int
    weight: float
    operations: list = field(default_factory=list)

    def ordered_operations(self):
        return sorted(self.operations, key=lambda o: o.position)

    @property
    def total_processing(self) -> int:
        return sum(o.duration for o in self.operations)
