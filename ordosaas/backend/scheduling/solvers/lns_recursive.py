"""
LNSRecursiveSolver : orchestrateur des 4 phases du Large Neighborhood Search recursif.
Gere les instances > SEUIL_EXACT jobs.
"""
import logging
import time
from typing import Callable, Optional

from scheduling.components.context_propagator import ContextPropagator
from scheduling.components.inter_window_optimizer import InterWindowOptimizer
from scheduling.components.window_manager import WindowManager
from scheduling.models.context import BoundaryContext
from scheduling.models.job import ProblemInstance
from scheduling.models.schedule import Schedule
from scheduling.models.window import Window, WindowResult
from scheduling.solvers.atcs_solver import ATCSSolver
from scheduling.solvers.base import BaseSolver
from scheduling.solvers.cpsat_solver import CPSATSolver

logger = logging.getLogger(__name__)

TAILLE_MIN = 5
PROFONDEUR_MAX = 4


class LNSRecursiveSolver(BaseSolver):
    """Strategie hybride LNS recursive en 4 phases."""

    def __init__(
        self, cpsat_timeout: int = 30, max_jobs_per_window: int = 50,
        min_jobs_per_window: int = 5, max_recursion_depth: int = PROFONDEUR_MAX,
        max_iterations: int = 5, epsilon: float = 0.01, junction_radius: int = 10,
        k1: float = None, k2: float = None,
        progress_callback: Optional[Callable] = None,
    ):
        self.cpsat_timeout = cpsat_timeout
        self.max_jobs_per_window = max_jobs_per_window
        self.min_jobs_per_window = min_jobs_per_window
        self.max_recursion_depth = max_recursion_depth
        self.max_iterations = max_iterations
        self.epsilon = epsilon
        self.junction_radius = junction_radius
        self.progress_callback = progress_callback

        self.atcs_solver = ATCSSolver(k1=k1, k2=k2)
        self.cpsat_solver = CPSATSolver(timeout_seconds=cpsat_timeout)
        self.window_manager = WindowManager(max_jobs_per_window, min_jobs_per_window)
        self.context_propagator = ContextPropagator()
        self.inter_window_optimizer = InterWindowOptimizer(
            cpsat_solver=self.cpsat_solver, max_iterations=max_iterations,
            epsilon=epsilon, junction_radius=junction_radius,
        )

    def solve(self, instance: ProblemInstance) -> Schedule:
        total_start = time.time()

        # PHASE 1: ATCS initial solution
        logger.info("Phase 1: Generating ATCS initial solution")
        self._notify_progress(1, "running", "Generation solution initiale ATCS")
        atcs_schedule = self.atcs_solver.solve(instance)
        atcs_twt = atcs_schedule.total_weighted_tardiness
        self._notify_progress(
            1, "completed", f"ATCS TWT={atcs_twt}", duration=time.time() - total_start
        )

        # PHASE 2: temporal windows
        logger.info("Phase 2: Creating temporal windows")
        self._notify_progress(2, "running", "Decoupage en fenetres temporelles")
        windows = self.window_manager.create_windows(instance, atcs_schedule)
        self._notify_progress(2, "completed", f"{len(windows)} fenetres creees", windows=windows)

        # PHASE 3: recursive divide & conquer
        logger.info("Phase 3: Recursive optimization")
        self._notify_progress(3, "running", "Optimisation recursive par fenetres")
        window_results = []
        left_context = BoundaryContext.empty()
        for i, window in enumerate(windows):
            right_context = None
            if i + 1 < len(windows):
                right_context = self.context_propagator.build_right_context(
                    windows[i + 1], atcs_schedule, instance
                )
            window_instance = self._create_window_instance(window, instance)
            result = self._optimize_window_recursive(
                window=window, instance=window_instance, full_instance=instance,
                left_context=left_context, right_context=right_context,
                atcs_schedule=atcs_schedule, depth=0,
            )
            window_results.append(result)
            left_context = self.context_propagator.build_left_context(result, instance)
            self._notify_progress(
                3, "running", f"Fenetre {i + 1}/{len(windows)}", window_result=result
            )
        self._notify_progress(3, "completed", "Toutes les fenetres optimisees")

        # PHASE 4: inter-window optimization
        logger.info("Phase 4: Inter-window optimization")
        self._notify_progress(4, "running", "Optimisation des jonctions inter-fenetres")
        final_schedule = self.inter_window_optimizer.optimize(
            window_results=window_results, instance=instance, atcs_schedule=atcs_schedule
        )

        final_twt = final_schedule.total_weighted_tardiness
        improvement = round((atcs_twt - final_twt) / max(atcs_twt, 1) * 100, 2)
        final_schedule.atcs_twt = atcs_twt
        final_schedule.improvement_vs_atcs_pct = improvement
        final_schedule.method_used = "lns"
        self._notify_progress(
            4, "completed", f"TWT final={final_twt}, amelioration={improvement}%"
        )
        logger.info(
            "LNS completed: ATCS=%s, LNS=%s, improvement=%s%%", atcs_twt, final_twt, improvement
        )
        return final_schedule

    def _optimize_window_recursive(
        self, window: Window, instance: ProblemInstance, full_instance: ProblemInstance,
        left_context: BoundaryContext, right_context: Optional[BoundaryContext],
        atcs_schedule: Schedule, depth: int,
    ) -> WindowResult:
        start_t = time.time()

        # Guard 1: minimal size
        if len(window.jobs) <= TAILLE_MIN:
            result = self.cpsat_solver.solve_with_context(instance, left_context, right_context)
            if result is None:
                result = self._atcs_fallback(window, instance, atcs_schedule)
            return WindowResult(
                window=window, schedule=result,
                exit_context=getattr(result, "exit_context", None) or BoundaryContext.empty(),
                objective=result.total_weighted_tardiness, method=result.method_used,
                duration_seconds=time.time() - start_t, recursion_depth=depth,
            )

        # Guard 2: max depth -> ATCS fallback
        if depth >= self.max_recursion_depth:
            logger.warning("Max recursion depth %d reached, ATCS fallback", self.max_recursion_depth)
            fallback = self._atcs_fallback(window, instance, atcs_schedule)
            return WindowResult(
                window=window, schedule=fallback,
                exit_context=getattr(fallback, "exit_context", None) or BoundaryContext.empty(),
                objective=fallback.total_weighted_tardiness, method="atcs_fallback",
                duration_seconds=time.time() - start_t, recursion_depth=depth,
            )

        # CP-SAT attempt
        result = self.cpsat_solver.solve_with_context(instance, left_context, right_context)
        if result is not None:
            return WindowResult(
                window=window, schedule=result,
                exit_context=getattr(result, "exit_context", None) or BoundaryContext.empty(),
                objective=result.total_weighted_tardiness, method=result.method_used,
                duration_seconds=time.time() - start_t, recursion_depth=depth,
            )

        # Timeout -> divide & conquer
        logger.info("CP-SAT timeout at depth %d, dividing window %d", depth, window.index)
        mid = len(window.jobs) // 2
        left_jobs = window.jobs[:mid]
        right_jobs = window.jobs[mid:]
        left_window = Window(
            index=window.index, t_start=window.t_start,
            t_end=(window.t_start + window.t_end) // 2, jobs=left_jobs,
        )
        right_window = Window(
            index=window.index, t_start=(window.t_start + window.t_end) // 2,
            t_end=window.t_end, jobs=right_jobs,
        )
        right_context_for_left = self.context_propagator.build_right_context(
            right_window, atcs_schedule, full_instance
        )
        left_instance = self._create_window_instance(left_window, full_instance)
        left_result = self._optimize_window_recursive(
            window=left_window, instance=left_instance, full_instance=full_instance,
            left_context=left_context, right_context=right_context_for_left,
            atcs_schedule=atcs_schedule, depth=depth + 1,
        )
        left_context_for_right = self.context_propagator.build_left_context(
            left_result, full_instance
        )
        right_instance = self._create_window_instance(right_window, full_instance)
        right_result = self._optimize_window_recursive(
            window=right_window, instance=right_instance, full_instance=full_instance,
            left_context=left_context_for_right, right_context=right_context,
            atcs_schedule=atcs_schedule, depth=depth + 1,
        )
        merged_schedule = self._merge_schedules(
            left_result.schedule, right_result.schedule, full_instance
        )
        return WindowResult(
            window=window, schedule=merged_schedule, exit_context=right_result.exit_context,
            objective=merged_schedule.total_weighted_tardiness,
            method=f"divide_and_conquer_d{depth}",
            duration_seconds=time.time() - start_t, recursion_depth=depth,
        )

    def _create_window_instance(
        self, window: Window, full_instance: ProblemInstance
    ) -> ProblemInstance:
        job_ids = {j.id for j in window.jobs}
        filtered_setups = {
            k: v for k, v in full_instance.setup_times.items()
            if k[0] in job_ids or k[1] in job_ids
        }
        return ProblemInstance(
            jobs=window.jobs, machines=full_instance.machines,
            setup_times=filtered_setups, wr=full_instance.wr,
        )

    def _atcs_fallback(
        self, window: Window, instance: ProblemInstance, atcs_schedule: Schedule
    ) -> Schedule:
        job_ids = {j.id for j in window.jobs}
        fallback = Schedule(method_used="atcs_fallback")
        for entry in atcs_schedule.entries:
            if entry.job_id in job_ids:
                fallback.add_entry(entry)
        for jr in atcs_schedule.jobs_result:
            if jr.job_id in job_ids:
                fallback.jobs_result.append(jr)
        fallback.total_weighted_tardiness = round(
            sum(jr.weighted_tardiness for jr in fallback.jobs_result), 4
        )
        return fallback

    def _merge_schedules(
        self, left: Schedule, right: Schedule, instance: ProblemInstance
    ) -> Schedule:
        merged = Schedule(method_used="merged")
        merged.entries = left.entries + right.entries
        merged.jobs_result = left.jobs_result + right.jobs_result
        merged.total_weighted_tardiness = round(
            sum(jr.weighted_tardiness for jr in merged.jobs_result), 4
        )
        return merged

    def _notify_progress(self, phase: int, status: str, detail: str, **kwargs):
        if self.progress_callback:
            self.progress_callback(phase=phase, status=status, detail=detail, **kwargs)
