"""
WindowManager : decoupe le planning ATCS initial en fenetres temporelles adaptatives.
"""
import logging

from scheduling.models.job import ProblemInstance
from scheduling.models.schedule import Schedule
from scheduling.models.window import Window

logger = logging.getLogger(__name__)

MAX_JOBS_PAR_FENETRE = 50
MIN_JOBS_PAR_FENETRE = 5


class WindowManager:
    """Decoupe le planning initial en fenetres temporelles adaptatives."""

    def __init__(
        self, max_jobs: int = MAX_JOBS_PAR_FENETRE, min_jobs: int = MIN_JOBS_PAR_FENETRE
    ):
        self.max_jobs = max_jobs
        self.min_jobs = min_jobs

    def create_windows(
        self, instance: ProblemInstance, atcs_schedule: Schedule
    ) -> list:
        jobs = instance.jobs
        if len(jobs) <= self.max_jobs:
            return [Window(index=1, t_start=0, t_end=instance.horizon, jobs=jobs)]

        jobs_sorted = sorted(jobs, key=lambda j: j.deadline)
        windows: list[Window] = []
        window_index = 1
        i = 0

        while i < len(jobs_sorted):
            chunk = jobs_sorted[i:i + self.max_jobs]
            if len(chunk) < self.min_jobs and windows:
                prev_window = windows[-1]
                merged_jobs = prev_window.jobs + chunk
                t_end = max(j.deadline for j in merged_jobs) + sum(
                    op.duration for j in merged_jobs for op in j.operations
                )
                windows[-1] = Window(
                    index=prev_window.index, t_start=prev_window.t_start,
                    t_end=t_end, jobs=merged_jobs,
                )
            else:
                t_start = windows[-1].t_end if windows else 0
                t_end = self._compute_window_end(chunk, t_start, atcs_schedule)
                windows.append(Window(
                    index=window_index, t_start=t_start, t_end=t_end, jobs=chunk
                ))
                window_index += 1
            i += self.max_jobs

        logger.info(
            "WindowManager created %d windows for %d jobs", len(windows), len(jobs)
        )
        return windows

    def _compute_window_end(self, jobs: list, t_start: int, schedule: Schedule) -> int:
        if not jobs:
            return t_start
        job_ids = {j.id for j in jobs}
        max_end = t_start
        for entry in schedule.entries:
            if entry.job_id in job_ids:
                max_end = max(max_end, entry.end_time)
        buffer = int(max_end * 0.1) + 10
        return max_end + buffer
