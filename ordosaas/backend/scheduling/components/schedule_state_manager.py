"""
ScheduleStateManager : separe un Schedule en partie figee et partie future selon T_now.

Regle fondamentale du reordonnancement incremental : tout ce qui precede T_now est
un fait accompli, pas une variable. Une entree dont `start_time <= T_now` est
TOUJOURS classee figee, y compris si elle n'est que partiellement entamee
(`start_time <= T_now < end_time`) : une operation commencee ne peut pas etre
deplacee, meme partiellement. C'est une contrainte dure, jamais une variable
d'optimisation.

La separation est une partition stricte : frozen_entries + future_entries
reconstitue exactement le Schedule d'origine, sans perte ni duplication. Les objets
ScheduleEntry ne sont pas copies, ce sont les memes instances.
"""
from dataclasses import dataclass, field


@dataclass
class ScheduleState:
    """Resultat de la separation d'un Schedule a un instant T_now donne."""

    t_now: int
    frozen_entries: list = field(default_factory=list)  # list[ScheduleEntry]
    future_entries: list = field(default_factory=list)  # list[ScheduleEntry]

    @property
    def in_progress_entries(self) -> list:
        """Entrees figees mais pas encore terminees a T_now (start <= T_now < end).

        Ce sont elles qui determinent a partir de quand chaque machine redevient
        disponible ; elles restent figees, on ne fait que lire leur end_time.
        """
        return [
            e for e in self.frozen_entries
            if e.start_time <= self.t_now < e.end_time
        ]

    @property
    def frozen_job_ids(self) -> set:
        return {e.job_id for e in self.frozen_entries}

    @property
    def future_job_ids(self) -> set:
        return {e.job_id for e in self.future_entries}

    @property
    def straddling_job_ids(self) -> set:
        """Jobs a cheval sur T_now : certaines operations figees, d'autres futures.

        Ces jobs sont le point d'attention des precedences : leurs operations
        futures doivent demarrer apres la fin de leurs operations figees.
        """
        return self.frozen_job_ids & self.future_job_ids

    def last_frozen_end_per_machine(self) -> dict:
        """{machine_id: fin de la derniere entree figee}, setups inclus.

        Une machine dont un setup fige deborde au-dela de la fin de l'operation
        n'est libre qu'a la fin de ce setup — d'ou le max sur les deux.
        """
        loads: dict = {}
        for e in self.frozen_entries:
            end = e.end_time
            if e.setup and e.setup.duration > 0:
                end = max(end, e.setup.end_time)
            if end > loads.get(e.machine_id, 0):
                loads[e.machine_id] = end
        return loads


class ScheduleStateManager:
    """Separe un Schedule existant en (frozen_entries, future_entries) selon T_now."""

    def split(self, schedule, t_now: int) -> ScheduleState:
        """Partitionne les entrees du Schedule autour de T_now.

        Args:
            schedule: le Schedule issu de la resolution precedente.
            t_now: l'instant present, dans la meme unite entiere que les
                start_time / end_time des ScheduleEntry.

        Returns:
            ScheduleState. La partition est stricte : aucune entree n'est perdue
            ni dupliquee, et les instances sont les memes que dans le Schedule
            d'origine.
        """
        if t_now < 0:
            raise ValueError(f"T_now doit etre >= 0, recu {t_now}")

        frozen, future = [], []
        for entry in schedule.entries:
            if entry.start_time <= t_now:
                frozen.append(entry)
            else:
                future.append(entry)
        return ScheduleState(t_now=t_now, frozen_entries=frozen, future_entries=future)
