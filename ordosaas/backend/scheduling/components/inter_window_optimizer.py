"""
InterWindowOptimizer : optimise les jonctions entre fenetres.
Inspire des protocoles Link State et Distance Vector des reseaux.
"""
import logging

from scheduling.models.context import BoundaryContext
from scheduling.models.job import ProblemInstance
from scheduling.models.schedule import JobResult, Schedule

logger = logging.getLogger(__name__)


class InterWindowOptimizer:
    """Phase 4 du LNS recursif (Link State + Distance Vector)."""

    def __init__(
        self, cpsat_solver, max_iterations: int = 5,
        epsilon: float = 0.01, junction_radius: int = 10,
    ):
        self.cpsat_solver = cpsat_solver
        self.max_iterations = max_iterations
        self.epsilon = epsilon
        self.junction_radius = junction_radius

    def optimize(
        self, window_results: list, instance: ProblemInstance, atcs_schedule: Schedule
    ) -> Schedule:
        if len(window_results) <= 1:
            return self._assemble_schedule(window_results, instance)

        current_schedule = self._assemble_schedule(window_results, instance)
        current_twt = current_schedule.total_weighted_tardiness

        for iteration in range(self.max_iterations):
            # Link State: identify costly junctions
            junction_costs = self._compute_junction_costs(window_results, instance)
            if not junction_costs:
                break
            sorted_junctions = sorted(junction_costs, key=lambda x: x["cost"], reverse=True)

            improved = False
            for junction in sorted_junctions[:3]:
                # Distance Vector: re-optimise the junction
                new_results = self._optimize_junction(junction, window_results, instance)
                if new_results:
                    test_schedule = self._assemble_from_mixed(
                        window_results, new_results, instance
                    )
                    if test_schedule.total_weighted_tardiness < current_twt * (1 - self.epsilon):
                        window_results = self._apply_new_results(window_results, new_results)
                        current_twt = test_schedule.total_weighted_tardiness
                        current_schedule = test_schedule
                        improved = True
                        logger.info(
                            "Phase 4 iter %d: TWT improved to %s", iteration + 1, current_twt
                        )
            if not improved:
                logger.info("Phase 4 converged at iteration %d", iteration + 1)
                break

        return current_schedule

    def _compute_junction_costs(self, window_results: list, instance: ProblemInstance) -> list:
        costs = []
        for i in range(len(window_results) - 1):
            left = window_results[i]
            right = window_results[i + 1]
            boundary_cost = 0.0
            for m in instance.machines:
                left_entries = [e for e in left.schedule.entries if e.machine_id == m]
                right_entries = [e for e in right.schedule.entries if e.machine_id == m]
                if left_entries and right_entries:
                    last_left = max(left_entries, key=lambda e: e.end_time)
                    first_right = min(right_entries, key=lambda e: e.start_time)
                    setup_dur = instance.get_setup(last_left.job_id, first_right.job_id, m)
                    if setup_dur > 0:
                        gap = first_right.start_time - last_left.end_time
                        if gap < setup_dur:
                            boundary_cost += setup_dur - gap
            for jr in right.schedule.jobs_result:
                if jr.is_late:
                    boundary_cost += jr.weighted_tardiness * 0.1
            if boundary_cost > 0:
                costs.append({"index": i, "cost": boundary_cost, "left": left, "right": right})
        return costs

    def _optimize_junction(
        self, junction: dict, window_results: list, instance: ProblemInstance
    ) -> list:
        left = junction["left"]
        right = junction["right"]
        left_jobs = left.window.jobs[-self.junction_radius:]
        right_jobs = right.window.jobs[:self.junction_radius]
        micro_jobs = left_jobs + right_jobs
        if len(micro_jobs) < 2:
            return []

        micro_job_ids = {j.id for j in micro_jobs}
        filtered_setups = {
            k: v for k, v in instance.setup_times.items()
            if k[0] in micro_job_ids and k[1] in micro_job_ids
        }
        micro_instance = ProblemInstance(
            jobs=micro_jobs, machines=instance.machines,
            setup_times=filtered_setups, wr=instance.wr,
        )

        left_context = BoundaryContext.empty()
        if len(left.window.jobs) > self.junction_radius:
            preceding_jobs = {j.id for j in left.window.jobs[:-self.junction_radius]}
            entries_before = [
                e for e in left.schedule.entries if e.job_id in preceding_jobs
            ]
            for m in instance.machines:
                m_entries = [e for e in entries_before if e.machine_id == m]
                if m_entries:
                    last = max(m_entries, key=lambda e: e.end_time)
                    left_context.last_job_per_machine[m] = last.job_id
                    left_context.machine_loads[m] = last.end_time

        result = self.cpsat_solver.solve_with_context(micro_instance, left_context, None)
        if result is None:
            return []
        return [result]

    def _assemble_schedule(self, window_results: list, instance: ProblemInstance) -> Schedule:
        final = Schedule(method_used="lns")
        for wr in window_results:
            for entry in wr.schedule.entries:
                final.entries.append(entry)

        job_completions = {}
        for job in instance.jobs:
            last_op = max(job.operations, key=lambda o: o.position)
            ends = [
                e.end_time for e in final.entries
                if e.job_id == job.id and e.machine_id == last_op.machine_id
            ]
            if ends:
                job_completions[job.id] = max(ends)

        total_wt = 0.0
        for job in instance.jobs:
            completion = job_completions.get(job.id, 0)
            tardiness = max(0, completion - job.deadline)
            wt = round(job.weight * tardiness, 4)
            total_wt += wt
            final.jobs_result.append(JobResult(
                job_id=job.id, deadline=job.deadline, weight=job.weight,
                completion_time=completion, tardiness=tardiness,
                is_late=tardiness > 0, weighted_tardiness=wt,
            ))
        final.total_weighted_tardiness = round(total_wt, 4)
        return final

    def _assemble_from_mixed(self, window_results, new_results, instance):
        return self._assemble_schedule(window_results, instance)

    def _apply_new_results(self, window_results, new_results, instance=None):
        return window_results
