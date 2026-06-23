"""Solver context: configuration passed to the dispatcher and solvers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SolverContext:
    wr: int = 5
    strategy: str = "auto"
    cpsat_timeout: int = 30
    max_jobs_per_window: int = 50
    min_jobs_per_window: int = 5
    max_recursion_depth: int = 4
    max_iterations: int = 5
    epsilon: float = 0.01
    junction_radius: int = 10
    k1: float | None = None
    k2: float | None = None
    seuil_exact: int = 50
