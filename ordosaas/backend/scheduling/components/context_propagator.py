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

        # Identify jobs straddling the boundary: scheduled in this window but
        # with operations still pending (their last op isn't this window's).
        total_ops = {j.id: len(j.operations) for j in instance.jobs}
        scheduled_positions: dict[str, int] = {}
        for e in schedule.entries:
            cur = scheduled_positions.get(e.job_id, 0)
            if e.position_in_job > cur:
                scheduled_positions[e.job_id] = e.position_in_job
        incomplete_jobs = {
            job_id: last_pos
            for job_id, last_pos in scheduled_positions.items()
            if last_pos < total_ops.get(job_id, last_pos)
        }

        return BoundaryContext(
            last_job_per_machine=last_job_per_machine,
            active_setups=self._setups_actifs(schedule, machine_loads),
            pending_jobs=pending_jobs, machine_loads=machine_loads,
            incomplete_jobs=incomplete_jobs,
        )

    @staticmethod
    def _setups_actifs(schedule: Schedule, machine_loads: dict) -> list:
        """Setups de la fenetre precedente pouvant encore consommer un technicien.

        Sans eux, la contrainte `Cumulative` WR n'etait appliquee qu'A L'INTERIEUR de
        chaque fenetre, jamais ENTRE elles : deux setups de fenetres voisines pouvaient
        se chevaucher librement, et le planning final du LNS etait rejete par le
        validateur canonique. Chaque fenetre etait pourtant valide isolement.

        Le champ existait deja et `CPSATSolver.solve_with_context` savait le consommer ;
        il n'etait simplement jamais rempli cote LNS. `IncrementalContextBuilder` le
        remplissait, lui, depuis le debut — son docstring precise meme « Ajout par
        rapport au LNS ».

        FILTRE. La frontiere retenue est la charge machine la PLUS PRECOCE : rien ne
        peut etre place avant elle, donc un setup qui s'acheve avant ne peut chevaucher
        aucun setup de la fenetre suivante. Les autres sont transmis — ce n'est pas une
        sur-reservation : pendant son propre intervalle, un setup consomme reellement un
        technicien.

        LIMITE ASSUMEE. `build_left_context` ne recoit que le resultat de la fenetre
        IMMEDIATEMENT precedente ; les setups de fenetres plus anciennes ne sont pas
        representes. Les fenetres etant sequentielles dans le temps, leurs setups
        s'achevent avant cette frontiere dans le cas courant. Elargir exigerait de
        changer la signature de cette methode, ce qui depasse la correction d'un defaut
        de validite.

        Format : [(machine_id, from_job_id, to_job_id, start_time, end_time)], celui que
        le solveur sait deja consommer.
        """
        if not machine_loads:
            return []
        frontiere = min(machine_loads.values())
        actifs = []
        for entry in schedule.entries:
            setup = entry.setup
            if setup is None or setup.duration <= 0:
                continue
            if setup.end_time > frontiere:
                actifs.append((
                    entry.machine_id, setup.from_job_id, entry.job_id,
                    setup.start_time, setup.end_time,
                ))
        return actifs

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
