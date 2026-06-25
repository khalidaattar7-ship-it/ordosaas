"""
SolverDispatcher : selectionne automatiquement le bon solveur selon l'instance.
Implemente le Strategy Pattern (Open/Closed principle).
"""
import logging

from scheduling.models.job import ProblemInstance
from scheduling.models.schedule import Schedule
from scheduling.solvers.atcs_solver import ATCSSolver
from scheduling.solvers.base import BaseSolver
from scheduling.solvers.cpsat_solver import CPSATSolver
from scheduling.solvers.lns_recursive import LNSRecursiveSolver

logger = logging.getLogger(__name__)

SEUIL_EXACT = 50  # CP-SAT direct si nb_jobs <= SEUIL_EXACT


class SolverDispatcher:
    """Route vers le bon solveur selon la taille de l'instance et la strategie."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.seuil_exact = self.config.get("seuil_exact", SEUIL_EXACT)

    def select_strategy(self, nb_jobs: int, strategy: str = "auto") -> str:
        """Resout la strategie 'auto' en un solveur concret."""
        if strategy == "cpsat":
            return "cpsat"
        if strategy == "atcs":
            return "atcs"
        if strategy == "lns":
            return "lns"
        return "cpsat" if nb_jobs <= self.seuil_exact else "lns"

    def dispatch(
        self, instance: ProblemInstance, strategy: str = "auto", progress_callback=None
    ) -> Schedule:
        nb_jobs = len(instance.jobs)
        solver = self._select_solver(nb_jobs, strategy, progress_callback)
        logger.info(
            "Dispatching to %s for %d jobs (strategy=%s)",
            solver.get_name(), nb_jobs, strategy,
        )
        schedule = solver.solve(instance)
        if schedule is not None:
            schedule.method_used = self._normalize_method(schedule.method_used, solver)
        return schedule

    @staticmethod
    def _normalize_method(method_used, solver) -> str:
        """Guarantee method_used names the solver (cpsat/lns/atcs).

        Some solvers historically stored a result status (optimal/feasible) in
        method_used; the DB constraint only accepts solver names, so coerce any
        unexpected value back to the concrete solver that produced it.
        """
        valid = {"cpsat", "lns", "atcs"}
        if method_used in valid:
            return method_used
        mapping = {
            "CPSATSolver": "cpsat",
            "ATCSSolver": "atcs",
            "LNSRecursiveSolver": "lns",
        }
        return mapping.get(solver.get_name(), "cpsat")

    def _select_solver(self, nb_jobs: int, strategy: str, progress_callback=None) -> BaseSolver:
        cpsat_timeout = self.config.get("cpsat_timeout", 30)
        max_jobs_per_window = self.config.get("max_jobs_per_window", 50)
        min_jobs_per_window = self.config.get("min_jobs_per_window", 5)
        max_recursion_depth = self.config.get("max_recursion_depth", 4)
        max_iterations = self.config.get("max_iterations", 5)
        epsilon = self.config.get("epsilon", 0.01)
        junction_radius = self.config.get("junction_radius", 10)
        k1 = self.config.get("k1", None)
        k2 = self.config.get("k2", None)

        resolved = self.select_strategy(nb_jobs, strategy)
        if resolved == "cpsat":
            return CPSATSolver(timeout_seconds=cpsat_timeout)
        if resolved == "atcs":
            return ATCSSolver(k1=k1, k2=k2)
        return LNSRecursiveSolver(
            cpsat_timeout=cpsat_timeout, max_jobs_per_window=max_jobs_per_window,
            min_jobs_per_window=min_jobs_per_window, max_recursion_depth=max_recursion_depth,
            max_iterations=max_iterations, epsilon=epsilon, junction_radius=junction_radius,
            k1=k1, k2=k2, progress_callback=progress_callback,
        )
