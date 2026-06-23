"""
ContextPropagator : construit et transmet les BoundaryContext entre fenetres.
"""
from scheduling.models.context import BoundaryContext
from scheduling.models.job import ProblemInstance
from scheduling.models.schedule import Schedule
from scheduling.models.window import Window, WindowResult


class ContextPropagator:
    """
    Regle fondamentale :
    - Contexte GAUCHE : toujours exact (resultat optimise de la fenetre precedente)
    - Contexte DROIT : toujours approximatif (planning ATCS initial)
    """

    def build_left_context(
        self, prev_result: WindowResult, instance: ProblemInstance
    ) -> BoundaryContext:
        """Contexte gauche EXACT depuis le resultat optimise precedent."""
        schedule = prev_result.schedule
        last_job_per_machine = {}
        machine_loads = {}
        for machine_id in instance.machines:
            entries_on_m = [e for e in schedule.entries if e.machine_id == machine_id]
            if entries_on_m:
                last_entry = max(entries_on_m, key=lambda e: e.end_time)
                last_job_per_machine[machine_id] = last_entry.job_id
                machine_loads[machine_id] = last_entry.end_time
        pending_jobs = list({e.job_id for e in schedule.entries})
        return BoundaryContext(
            last_job_per_machine=last_job_per_machine, active_setups=[],
            pending_jobs=pending_jobs, machine_loads=machine_loads,
        )

    def build_right_context(
        self, next_window: Window, atcs_schedule: Schedule, instance: ProblemInstance
    ) -> BoundaryContext:
        """Contexte droit APPROXIMATIF depuis le planning ATCS."""
        next_job_ids = {j.id for j in next_window.jobs}
        first_job_per_machine = {}
        for machine_id in instance.machines:
            entries_on_m = [
                e for e in atcs_schedule.entries
                if e.machine_id == machine_id and e.job_id in next_job_ids
            ]
            if entries_on_m:
                first_entry = min(entries_on_m, key=lambda e: e.start_time)
                first_job_per_machine[machine_id] = first_entry.job_id
        return BoundaryContext(
            last_job_per_machine=first_job_per_machine, active_setups=[],
            pending_jobs=list(next_job_ids), machine_loads={},
        )
