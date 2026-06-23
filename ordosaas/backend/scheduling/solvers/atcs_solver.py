"""
Heuristique ATCS (Apparent Tardiness Cost with Setups).
Utilisee comme solution initiale pour le LNS et comme fallback pour grandes instances.
Basee sur Avgerinos et al. (2023).
"""
import logging
import math
import time

from scheduling.models.job import ProblemInstance
from scheduling.models.schedule import JobResult, Schedule, ScheduleEntry, SetupEntry
from scheduling.solvers.base import BaseSolver

logger = logging.getLogger(__name__)


class ATCSSolver(BaseSolver):
    """Heuristique de dispatching ATCS."""

    def __init__(self, k1: float = None, k2: float = None):
        self.k1 = k1
        self.k2 = k2

    def solve(self, instance: ProblemInstance) -> Schedule:
        start_time = time.time()
        jobs = instance.jobs
        machines = instance.machines

        p_bar = self._mean_processing_time(jobs)
        s_bar = self._mean_setup_time(instance)
        k1 = self.k1 if self.k1 else self._calibrate_k1(jobs)
        k2 = self.k2 if self.k2 else 1.0

        machine_time = {m: 0 for m in machines}
        last_job_on_machine = {m: None for m in machines}
        job_op_end = {job.id: 0 for job in jobs}

        schedule = Schedule(method_used="atcs")

        # Queue of next-to-schedule operation per job
        pending_ops = []
        for job in jobs:
            ops_sorted = sorted(job.operations, key=lambda o: o.position)
            if ops_sorted:
                pending_ops.append((job, ops_sorted[0]))

        max_ops = max((len(j.operations) for j in jobs), default=1)
        max_iter = len(jobs) * max_ops * 10 + 10
        iteration = 0

        while pending_ops and iteration < max_iter:
            iteration += 1
            best_machine = min(machines, key=lambda m: machine_time[m])
            current_time = machine_time[best_machine]

            best_score = -float("inf")
            best_job = None
            best_op = None
            for job, op in pending_ops:
                if op.machine_id != best_machine:
                    continue
                if op.position > 1 and job_op_end.get(job.id, 0) == 0:
                    continue  # previous op not yet scheduled

                last_j = last_job_on_machine[best_machine]
                s_dur = instance.get_setup(last_j, job.id, best_machine) if last_j else 0
                earliest_start = max(current_time, job_op_end[job.id]) + s_dur

                slack = max(job.deadline - op.duration, 0)
                urgency = math.exp(
                    -max(slack - earliest_start, 0) / max(k1 * p_bar, 1e-9)
                )
                setup_factor = (
                    math.exp(-s_dur / max(k2 * s_bar, 1e-9)) if s_bar > 0 else 1.0
                )
                score = (job.weight / max(op.duration, 1)) * urgency * setup_factor
                if score > best_score:
                    best_score, best_job, best_op = score, job, op

            if best_job is None:
                # No op available on this machine — advance time
                next_available = float("inf")
                for job, op in pending_ops:
                    prev_end = job_op_end[job.id]
                    if prev_end > machine_time[op.machine_id]:
                        next_available = min(next_available, prev_end)
                if next_available == float("inf"):
                    machine_time[best_machine] += 1
                else:
                    machine_time[best_machine] = next_available
                continue

            last_j = last_job_on_machine[best_machine]
            s_dur = instance.get_setup(last_j, best_job.id, best_machine) if last_j else 0
            earliest_start = max(machine_time[best_machine], job_op_end[best_job.id])
            actual_start = earliest_start + s_dur

            setup_entry = None
            if s_dur > 0:
                setup_entry = SetupEntry(
                    from_job_id=last_j, start_time=earliest_start,
                    end_time=actual_start, duration=s_dur,
                )

            actual_end = actual_start + best_op.duration
            schedule.add_entry(ScheduleEntry(
                job_id=best_job.id, machine_id=best_machine,
                position_in_job=best_op.position, start_time=actual_start,
                end_time=actual_end, duration=best_op.duration, setup=setup_entry,
            ))

            machine_time[best_machine] = actual_end
            last_job_on_machine[best_machine] = best_job.id
            job_op_end[best_job.id] = actual_end

            pending_ops.remove((best_job, best_op))
            ops_sorted = sorted(best_job.operations, key=lambda o: o.position)
            next_pos = best_op.position  # 1-indexed; list index of next op
            if next_pos < len(ops_sorted):
                pending_ops.append((best_job, ops_sorted[next_pos]))

        # KPIs
        job_completion = {}
        for entry in schedule.entries:
            job = next(j for j in jobs if j.id == entry.job_id)
            last_op = max(job.operations, key=lambda o: o.position)
            if entry.machine_id == last_op.machine_id:
                job_completion[entry.job_id] = max(
                    job_completion.get(entry.job_id, 0), entry.end_time
                )

        total_wtard = 0.0
        for job in jobs:
            completion = job_completion.get(job.id, 0)
            tardiness = max(0, completion - job.deadline)
            wt = round(job.weight * tardiness, 4)
            total_wtard += wt
            schedule.jobs_result.append(JobResult(
                job_id=job.id, deadline=job.deadline, weight=job.weight,
                completion_time=completion, tardiness=tardiness,
                is_late=tardiness > 0, weighted_tardiness=wt,
            ))

        schedule.total_weighted_tardiness = round(total_wtard, 4)
        logger.info(
            "ATCS completed in %.3fs, TWT=%s",
            time.time() - start_time, schedule.total_weighted_tardiness,
        )
        return schedule

    def _mean_processing_time(self, jobs) -> float:
        all_durations = [op.duration for job in jobs for op in job.operations]
        return sum(all_durations) / len(all_durations) if all_durations else 1.0

    def _mean_setup_time(self, instance: ProblemInstance) -> float:
        non_zero = [s for s in instance.setup_times.values() if s > 0]
        return sum(non_zero) / len(non_zero) if non_zero else 0.0

    def _calibrate_k1(self, jobs) -> float:
        """Calibrage automatique de k1 selon le serrage des delais (Avgerinos)."""
        deadlines = [j.deadline for j in jobs]
        durations = [sum(op.duration for op in j.operations) for j in jobs]
        if not deadlines or not durations:
            return 1.0
        avg_deadline = sum(deadlines) / len(deadlines)
        avg_duration = sum(durations) / len(durations)
        tightness = avg_duration / avg_deadline if avg_deadline > 0 else 0.5
        return max(0.1, min(2.0, 1.0 / max(tightness, 0.1)))
