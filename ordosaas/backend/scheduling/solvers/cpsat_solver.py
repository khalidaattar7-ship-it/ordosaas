"""
Solveur CP-SAT pour l'ordonnancement a retard pondere minimal.
Gere les setups sequence-dependants et les ressources renouvelables (WR).
Base sur Avgerinos et al. (2023).
"""
import logging
import time
from typing import Optional

from ortools.sat.python import cp_model

from scheduling.models.context import BoundaryContext
from scheduling.models.job import ProblemInstance
from scheduling.models.schedule import JobResult, Schedule, ScheduleEntry, SetupEntry
from scheduling.solvers.base import BaseSolver

logger = logging.getLogger(__name__)


def _borne_horizon(instance) -> int:
    """Majorant du makespan, resserre (cf. D12).

    `ProblemInstance.horizon` majore les setups par la somme de TOUTES les paires
    declarees. C'est un majorant herite du defaut H8 : tant qu'aucun setup n'etait
    jamais paye, la largeur du domaine n'avait pas d'incidence. Une fois les setups
    reellement contraints, elle en a une — sur l'instance d'exemple, ce majorant vaut
    5022 pour un makespan reellement atteint de 673, soit des domaines de variables
    7,5 fois plus larges que necessaire.

    La borne retenue s'appuie sur le fait qu'en toute solution, une operation ne peut
    avoir qu'UN setup entrant. On majore donc, machine par machine, chaque setup
    entrant par le plus long setup possible vers cette operation, ce qui reste un
    majorant valide meme dans le pire cas ou tout serait execute sequentiellement.
    """
    duree_totale = sum(op.duration for job in instance.jobs for op in job.operations)

    borne_setups = 0
    for machine_id in instance.machines:
        jobs_on_m = [
            j for j in instance.jobs
            if any(op.machine_id == machine_id for op in j.operations)
        ]
        for to_job in jobs_on_m:
            entrants = [
                instance.get_setup(from_job.id, to_job.id, machine_id)
                for from_job in jobs_on_m if from_job.id != to_job.id
            ]
            borne_setups += max(entrants, default=0)
    return duree_totale + borne_setups


class CPSATSolver(BaseSolver):
    """Solveur exact CP-SAT pour instances <= SEUIL_EXACT jobs."""

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    def solve(self, instance: ProblemInstance) -> Schedule:
        """Resolution complete sans contexte."""
        return self.solve_with_context(instance, BoundaryContext.empty(), None)

    def solve_with_context(
        self,
        instance: ProblemInstance,
        left_context: BoundaryContext,
        right_context: Optional[BoundaryContext],
    ) -> Optional[Schedule]:
        """Resolution avec contexte de frontiere (pour le LNS recursif)."""
        start_time = time.time()
        model = cp_model.CpModel()

        jobs = instance.jobs
        machines = instance.machines
        horizon = max(1, _borne_horizon(instance))

        # Account for left-context machine loads in the horizon.
        if left_context.machine_loads:
            horizon += max(left_context.machine_loads.values())

        # Interval variables per operation
        op_vars = {}
        for job in jobs:
            for op in job.operations:
                s = model.NewIntVar(0, horizon, f"s_{job.id}_{op.machine_id}")
                e = model.NewIntVar(0, horizon, f"e_{job.id}_{op.machine_id}")
                iv = model.NewIntervalVar(s, op.duration, e, f"iv_{job.id}_{op.machine_id}")
                op_vars[(job.id, op.machine_id)] = (s, e, iv, op.duration, op.position)

        # Precedence constraints (job-internal sequence)
        for job in jobs:
            ops_sorted = sorted(job.operations, key=lambda o: o.position)
            for k in range(len(ops_sorted) - 1):
                op1, op2 = ops_sorted[k], ops_sorted[k + 1]
                _, e1, _, _, _ = op_vars[(job.id, op1.machine_id)]
                s2, _, _, _, _ = op_vars[(job.id, op2.machine_id)]
                model.Add(s2 >= e1)

        # Left-context exact boundaries (earliest start per machine)
        for machine_id, last_end_time in left_context.machine_loads.items():
            for job in jobs:
                for op in job.operations:
                    if op.machine_id == machine_id:
                        s, _, _, _, _ = op_vars[(job.id, machine_id)]
                        model.Add(s >= last_end_time)

        # ------------------------------------------------------------------
        # Sequencement par machine et setups sequence-dependants (cf. D12)
        # ------------------------------------------------------------------
        # Une contrainte de CIRCUIT par machine. Les noeuds sont le depot (0) et
        # les jobs presents sur la machine ; un arc i -> j porte le litteral
        # "j suit IMMEDIATEMENT i sur cette machine".
        #
        # AddCircuit garantit STRUCTURELLEMENT que chaque job a exactement un
        # predecesseur et un successeur : le litteral d'arc de la paire reellement
        # consecutive vaut donc necessairement 1, et le setup correspondant est
        # necessairement paye.
        #
        # C'est ce qui manquait et qui constituait le defaut H8 : les booleens de
        # setup existaient mais rien ne les forcait, si bien que CP-SAT les mettait
        # tous a zero et ne payait jamais aucun setup. Voir docs/CONTEXTE_ET_DECISIONS.md.
        #
        # Un arc est cree pour CHAQUE paire ordonnee, y compris a setup nul : le
        # circuit ne serait pas hamiltonien sinon, et la garantie tomberait.
        setup_vars = {}
        for machine_id in machines:
            jobs_on_m = [
                j for j in jobs if any(op.machine_id == machine_id for op in j.operations)
            ]
            if len(jobs_on_m) < 2:
                continue  # pas de sequencement a arbitrer sur cette machine

            # Indices de noeud : 0 = depot, k + 1 = jobs_on_m[k].
            arcs = []
            for k, job in enumerate(jobs_on_m):
                arcs.append((0, k + 1, model.NewBoolVar(f"debut_{job.id}_{machine_id}")))
                arcs.append((k + 1, 0, model.NewBoolVar(f"fin_{job.id}_{machine_id}")))

            for i, from_job in enumerate(jobs_on_m):
                for j, to_job in enumerate(jobs_on_m):
                    if i == j:
                        continue
                    b = model.NewBoolVar(f"b_{from_job.id}_{to_job.id}_{machine_id}")
                    arcs.append((i + 1, j + 1, b))

                    s_dur = instance.get_setup(from_job.id, to_job.id, machine_id)
                    ef = op_vars[(from_job.id, machine_id)][1]
                    st = op_vars[(to_job.id, machine_id)][0]

                    # Le setup separe les deux operations des qu'elles se suivent.
                    # Vrai aussi quand s_dur vaut 0 : l'arc impose alors le simple
                    # ordre, ce qui renforce la propagation du NoOverlap.
                    model.Add(st >= ef + s_dur).OnlyEnforceIf(b)

                    if s_dur == 0:
                        continue

                    # L'intervalle de setup reste OPTIONNEL, mais il est desormais
                    # gouverne par le litteral d'arc et non par un booleen libre.
                    # Il continue d'alimenter le NoOverlap machine et la Cumulative
                    # WR sans changement en aval.
                    ss = model.NewIntVar(0, horizon, f"ss_{from_job.id}_{to_job.id}_{machine_id}")
                    se = model.NewIntVar(0, horizon, f"se_{from_job.id}_{to_job.id}_{machine_id}")
                    siv = model.NewOptionalIntervalVar(
                        ss, s_dur, se, b, f"siv_{from_job.id}_{to_job.id}_{machine_id}"
                    )
                    model.Add(ss >= ef).OnlyEnforceIf(b)
                    model.Add(se <= st).OnlyEnforceIf(b)
                    setup_vars[(from_job.id, to_job.id, machine_id)] = (ss, se, siv, b, s_dur)

            model.AddCircuit(arcs)

        # Setups from the left context (last job on each machine)
        for machine_id, last_job_id in left_context.last_job_per_machine.items():
            for to_job in jobs:
                if not any(op.machine_id == machine_id for op in to_job.operations):
                    continue
                s_dur = instance.get_setup(last_job_id, to_job.id, machine_id)
                if s_dur > 0:
                    load = left_context.machine_loads.get(machine_id, 0)
                    s_to, _, _, _, _ = op_vars[(to_job.id, machine_id)]
                    model.Add(s_to >= load + s_dur)

        # NoOverlap per machine (operations + setups)
        for machine_id in machines:
            intervals = []
            for job in jobs:
                if any(op.machine_id == machine_id for op in job.operations):
                    _, _, iv, _, _ = op_vars[(job.id, machine_id)]
                    intervals.append(iv)
            for (fi, ti, km), (ss, se, siv, b, _) in setup_vars.items():
                if km == machine_id:
                    intervals.append(siv)
            if intervals:
                model.AddNoOverlap(intervals)

        # Cumulative constraint on setups (WR technicians)
        all_setup_intervals = []
        all_setup_demands = []
        for (fi, ti, m), (ss, se, siv, b, dur) in setup_vars.items():
            all_setup_intervals.append(siv)
            all_setup_demands.append(1)
        for active_setup in left_context.active_setups:
            machine_id, from_j, to_j, s_time, e_time = active_setup
            if e_time > s_time:
                fixed_iv = model.NewIntervalVar(
                    model.NewConstant(s_time), e_time - s_time, model.NewConstant(e_time),
                    f"active_setup_{machine_id}_{from_j}_{to_j}",
                )
                all_setup_intervals.append(fixed_iv)
                all_setup_demands.append(1)
        if all_setup_intervals and instance.wr > 0:
            model.AddCumulative(all_setup_intervals, all_setup_demands, instance.wr)

        # Completion times, tardiness and objective
        completion_times = {}
        for job in jobs:
            last_op = max(job.operations, key=lambda o: o.position)
            _, e_last, _, _, _ = op_vars[(job.id, last_op.machine_id)]
            completion_times[job.id] = e_last

        tardiness_vars = {}
        zero = model.NewConstant(0)
        for job in jobs:
            t = model.NewIntVar(0, horizon, f"tard_{job.id}")
            model.AddMaxEquality(t, [completion_times[job.id] - job.deadline, zero])
            tardiness_vars[job.id] = t

        objective_terms = [int(job.weight * 100) * tardiness_vars[job.id] for job in jobs]
        model.Minimize(sum(objective_terms))

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(self.timeout_seconds)
        solver.parameters.num_search_workers = 4
        status = solver.Solve(model)

        elapsed = time.time() - start_time
        logger.info(
            "CP-SAT status=%s in %.2fs", solver.StatusName(status), elapsed
        )

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None  # Signal failure to the recursive optimizer

        # Build Schedule. method_used must name the SOLVER (cpsat) for the DB
        # constraint; the optimal/feasible outcome goes into solver_status.
        schedule = Schedule(
            method_used="cpsat",
            solver_status="optimal" if status == cp_model.OPTIMAL else "feasible",
        )
        for job in jobs:
            for op in job.operations:
                s_val = solver.Value(op_vars[(job.id, op.machine_id)][0])
                e_val = solver.Value(op_vars[(job.id, op.machine_id)][1])

                setup_entry = None
                for (fi, ti, km), (ss, se, siv, b, sd) in setup_vars.items():
                    if ti == job.id and km == op.machine_id and solver.Value(b) == 1:
                        setup_entry = SetupEntry(
                            from_job_id=fi, start_time=solver.Value(ss),
                            end_time=solver.Value(se), duration=sd,
                        )
                        break
                if setup_entry is None:
                    last_job = left_context.last_job_per_machine.get(op.machine_id)
                    if last_job:
                        s_dur = instance.get_setup(last_job, job.id, op.machine_id)
                        if s_dur > 0:
                            load = left_context.machine_loads.get(op.machine_id, 0)
                            setup_entry = SetupEntry(
                                from_job_id=last_job, start_time=load,
                                end_time=load + s_dur, duration=s_dur,
                            )

                schedule.add_entry(ScheduleEntry(
                    job_id=job.id, machine_id=op.machine_id, position_in_job=op.position,
                    start_time=s_val, end_time=e_val, duration=op.duration, setup=setup_entry,
                ))

        for job in jobs:
            tard = solver.Value(tardiness_vars[job.id])
            completion = solver.Value(completion_times[job.id])
            schedule.jobs_result.append(JobResult(
                job_id=job.id, deadline=job.deadline, weight=job.weight,
                completion_time=completion, tardiness=tard, is_late=tard > 0,
                weighted_tardiness=round(job.weight * tard, 4),
            ))

        schedule.total_weighted_tardiness = round(solver.ObjectiveValue() / 100, 4)
        exit_context = self._build_exit_context(schedule, instance)
        schedule.exit_context = exit_context
        return schedule

    def _build_exit_context(self, schedule: Schedule, instance: ProblemInstance) -> BoundaryContext:
        """Construit le BoundaryContext de sortie a partir de cette fenetre."""
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
