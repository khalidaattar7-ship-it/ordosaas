"""Solver dispatcher: selects a strategy and produces a feasible schedule.

This implementation provides a deterministic ATCS-style list-scheduling
heuristic that yields a valid non-preemptive job-shop schedule honouring
operation precedence (by position), machine no-overlap and sequence-dependent
setup times. The exact (CP-SAT) and windowed (LNS) solvers are scaffolded in
``scheduling/solvers`` and will refine this baseline.
"""
from __future__ import annotations

import math

from scheduling.models import Job, Schedule, ScheduledOperation, SolverContext, Window


class SolverDispatcher:
    def __init__(self, context: SolverContext):
        self.ctx = context

    # -- strategy selection -------------------------------------------------
    def select_strategy(self, jobs: list[Job]) -> str:
        if self.ctx.strategy != "auto":
            return self.ctx.strategy
        return "cpsat" if len(jobs) <= self.ctx.seuil_exact else "lns"

    # -- ATCS priority index ------------------------------------------------
    def _atcs_priority(self, job: Job, t: int, p_avg: float) -> float:
        slack = job.deadline - t - job.total_processing
        k1 = self.ctx.k1 or 1.0
        k2 = self.ctx.k2 or 1.0
        p = max(1, job.total_processing)
        urgency = math.exp(-max(0.0, slack) / (k1 * p_avg)) if p_avg > 0 else 1.0
        return (job.weight / p) * urgency / (k2 if k2 else 1.0)

    # -- core list scheduling ----------------------------------------------
    def _schedule_jobs(
        self, jobs: list[Job], setups: dict, method: str
    ) -> Schedule:
        machine_free: dict[str, int] = {}
        machine_last_job: dict[str, str] = {}
        job_ready: dict[str, int] = {j.job_id: 0 for j in jobs}
        entries: list[ScheduledOperation] = []
        total_setup = 0
        p_avg = (sum(j.total_processing for j in jobs) / len(jobs)) if jobs else 1.0

        remaining = list(jobs)
        # Order jobs by ATCS priority at t=0 (stable, deterministic).
        remaining.sort(key=lambda j: self._atcs_priority(j, 0, p_avg), reverse=True)

        for job in remaining:
            for op in job.ordered_operations():
                m = op.machine_id
                m_free = machine_free.get(m, 0)
                prev_job = machine_last_job.get(m)
                setup = setups.get((prev_job, job.job_id, m), 0) if prev_job else 0
                earliest = max(job_ready[job.job_id], m_free)
                setup_start = earliest if setup else None
                setup_end = earliest + setup if setup else None
                start = earliest + setup
                end = start + op.duration
                entries.append(ScheduledOperation(
                    job_id=job.job_id, op_id=op.op_id, machine_id=m, position=op.position,
                    start_time=start, end_time=end,
                    setup_from_job=prev_job if setup else None,
                    setup_start_time=setup_start, setup_end_time=setup_end,
                    setup_duration=setup, window_index=1,
                ))
                machine_free[m] = end
                machine_last_job[m] = job.job_id
                job_ready[job.job_id] = end
                total_setup += setup

        return self._finalize(jobs, entries, total_setup, method)

    def _finalize(self, jobs, entries, total_setup, method) -> Schedule:
        sched = Schedule(entries=entries, method_used=method, total_setup_time=total_setup)
        horizon = max((e.end_time for e in entries), default=0)
        sched.horizon = horizon

        twt = 0.0
        max_tard = 0.0
        late = 0
        for job in jobs:
            completion = max(
                (e.end_time for e in entries if e.job_id == job.job_id), default=0
            )
            tard = max(0, completion - job.deadline)
            sched.job_completion[job.job_id] = completion
            sched.job_tardiness[job.job_id] = tard
            twt += job.weight * tard
            max_tard = max(max_tard, tard)
            if tard > 0:
                late += 1
        sched.total_weighted_tardiness = round(twt, 4)
        sched.nb_jobs_late = late
        sched.nb_jobs_on_time = len(jobs) - late
        sched.max_tardiness = float(max_tard)

        # Machine utilisation = busy / (horizon * nb_machines)
        machines = {e.machine_id for e in entries}
        if machines and horizon > 0:
            busy = sum(e.end_time - e.start_time for e in entries)
            sched.machine_utilization_pct = round(
                100.0 * busy / (horizon * len(machines)), 2
            )

        # Single covering window
        sched.windows = [Window(
            index=1, t_start=0, t_end=max(1, horizon),
            job_ids=[j.job_id for j in jobs], status="feasible",
            method_used=method, local_weighted_tardiness=sched.total_weighted_tardiness,
        )]
        return sched

    # -- public entrypoint --------------------------------------------------
    def solve(self, jobs: list[Job], setups: dict | None = None) -> Schedule:
        setups = setups or {}
        method = self.select_strategy(jobs)

        # ATCS baseline (also used as comparison reference)
        atcs = self._schedule_jobs(jobs, setups, "atcs")

        if method == "atcs":
            atcs.atcs_weighted_tardiness = atcs.total_weighted_tardiness
            atcs.improvement_vs_atcs_pct = 0.0
            return atcs

        # cpsat / lns currently reuse the heuristic baseline; record the
        # ATCS reference so the improvement KPI is meaningful once exact
        # solvers are plugged in.
        result = self._schedule_jobs(jobs, setups, method)
        result.atcs_weighted_tardiness = atcs.total_weighted_tardiness
        if atcs.total_weighted_tardiness > 0:
            improvement = (
                (atcs.total_weighted_tardiness - result.total_weighted_tardiness)
                / atcs.total_weighted_tardiness * 100.0
            )
            result.improvement_vs_atcs_pct = round(improvement, 2)
        else:
            result.improvement_vs_atcs_pct = 0.0
        return result
