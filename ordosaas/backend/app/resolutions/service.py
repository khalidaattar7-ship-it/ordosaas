"""Resolutions business logic with asynchronous solver dispatch."""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.errors import bad_request, not_found
from app.models.instance import ProblemInstance
from app.models.job import Job
from app.models.machine import Machine
from app.models.operation import Operation
from app.models.resolution import Resolution
from app.models.schedule_entry import ScheduleEntry
from app.models.setup_time import SetupTime
from app.models.solver_config import SolverConfig
from app.models.time_window import TimeWindow
from app.resolutions.schemas import (
    GanttEntry,
    GanttResponse,
    JobDetailInResolution,
    KPIs,
    MachineSummary,
    OperationInSchedule,
    ResolutionStatus,
    ResolveResponse,
    SetupInfo,
    WindowSummary,
)
from scheduling.dispatcher import SolverDispatcher
from scheduling.models import Job as SJob
from scheduling.models import Operation as SOperation
from scheduling.models import ProblemInstance as SInstance


def _config_dict(config: SolverConfig) -> dict:
    return {
        "cpsat_timeout": config.cpsat_timeout,
        "max_jobs_per_window": config.max_jobs_per_window,
        "min_jobs_per_window": config.min_jobs_per_window,
        "max_recursion_depth": config.max_recursion_depth,
        "max_iterations": config.max_iterations,
        "epsilon": float(config.epsilon),
        "junction_radius": config.junction_radius,
        "k1": float(config.k1) if config.k1 is not None else None,
        "k2": float(config.k2) if config.k2 is not None else None,
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# resolve(): create config + resolution, then run solver in the background
# --------------------------------------------------------------------------
async def resolve(instance_id, config_data, tenant_id, user_id, db: AsyncSession) -> ResolveResponse:
    inst = await db.get(ProblemInstance, instance_id)
    if inst is None or inst.tenant_id != tenant_id:
        raise not_found("Instance introuvable")
    if inst.nb_jobs == 0:
        raise bad_request("L'instance ne contient aucun job")

    config = SolverConfig(
        tenant_id=tenant_id, instance_id=instance_id, created_by=user_id,
        wr=config_data.wr, strategy=config_data.strategy,
        cpsat_timeout=config_data.cpsat_timeout,
        max_jobs_per_window=config_data.max_jobs_per_window,
        min_jobs_per_window=config_data.min_jobs_per_window,
        max_recursion_depth=config_data.max_recursion_depth,
        max_iterations=config_data.max_iterations,
        epsilon=config_data.epsilon, junction_radius=config_data.junction_radius,
        k1=config_data.k1, k2=config_data.k2,
    )
    db.add(config)
    await db.flush()

    resolution = Resolution(
        tenant_id=tenant_id, instance_id=instance_id, config_id=config.id,
        triggered_by=user_id, status="pending", progress_pct=0, current_phase=0,
    )
    db.add(resolution)
    inst.status = "solving"
    await db.commit()
    await db.refresh(resolution)

    strategy_selected = SolverDispatcher(_config_dict(config)).select_strategy(
        inst.nb_jobs, config.strategy
    )
    estimated = min(config.cpsat_timeout, 5 + inst.nb_jobs // 10)

    # Launch background resolution (detached task).
    asyncio.create_task(_run_resolution_async(resolution.id))

    return ResolveResponse(
        resolution_id=resolution.id, instance_id=instance_id, status="pending",
        estimated_duration_seconds=estimated, strategy_selected=strategy_selected,
        created_at=resolution.created_at,
    )


async def _load_scheduling_input(db, instance_id, tenant_id):
    jrows = await db.execute(
        select(Job).where(Job.instance_id == instance_id)
        .options(selectinload(Job.operations))
    )
    db_jobs = jrows.scalars().all()
    srows = await db.execute(select(SetupTime).where(SetupTime.instance_id == instance_id))
    setups_db = srows.scalars().all()

    ext_by_job = {j.id: j.external_id for j in db_jobs}
    sjobs = []
    op_lookup = {}
    machine_ids: set[str] = set()
    for j in db_jobs:
        s_ops = []
        for o in j.operations:
            mid = str(o.machine_id)
            machine_ids.add(mid)
            s_ops.append(SOperation(
                job_id=j.external_id, machine_id=mid,
                duration=o.duration, position=o.position,
            ))
            op_lookup[(j.external_id, o.position)] = o
        sjobs.append(SJob(
            id=j.external_id, operations=s_ops, deadline=j.deadline, weight=float(j.weight)
        ))

    setups = {}
    for s in setups_db:
        setups[(ext_by_job.get(s.from_job_id), ext_by_job.get(s.to_job_id), str(s.machine_id))] = s.duration

    return db_jobs, sjobs, setups, op_lookup, sorted(machine_ids)


# --------------------------------------------------------------------------
# _run_resolution_async(): the background worker (own DB session)
# --------------------------------------------------------------------------
async def _run_resolution_async(resolution_id) -> None:
    async with AsyncSessionLocal() as db:
        resolution = await db.get(Resolution, resolution_id)
        if resolution is None:
            return
        config = await db.get(SolverConfig, resolution.config_id)
        instance = await db.get(ProblemInstance, resolution.instance_id)
        try:
            resolution.status = "running"
            resolution.started_at = _now()
            resolution.progress_pct = 5
            resolution.current_phase = 1
            resolution.progress_detail = {"phase": 1, "label": "Chargement des donnees"}
            await db.commit()

            db_jobs, sjobs, setups, op_lookup, machine_ids = \
                await _load_scheduling_input(db, resolution.instance_id, resolution.tenant_id)

            resolution.current_phase = 2
            resolution.progress_pct = 30
            resolution.progress_detail = {"phase": 2, "label": "Decoupage en fenetres"}
            await db.commit()

            s_instance = SInstance(
                jobs=sjobs, machines=machine_ids, setup_times=setups, wr=config.wr
            )

            resolution.current_phase = 3
            resolution.progress_pct = 60
            resolution.progress_detail = {"phase": 3, "label": "Resolution"}
            await db.commit()

            schedule = SolverDispatcher(_config_dict(config)).dispatch(
                s_instance, config.strategy
            )
            if schedule is None:
                raise RuntimeError("Le solveur n'a retourne aucune solution realisable")

            resolution.current_phase = 4
            resolution.progress_pct = 90
            resolution.progress_detail = {"phase": 4, "label": "Sauvegarde des resultats"}
            await db.commit()

            # Persist a single covering window
            horizon = schedule.horizon
            tw = TimeWindow(
                tenant_id=resolution.tenant_id, resolution_id=resolution.id,
                window_index=1, t_start=0, t_end=max(1, horizon),
                nb_jobs=max(1, len(db_jobs)), status="feasible",
                method_used=schedule.method_used, recursion_depth=0,
                local_weighted_tardiness=schedule.total_weighted_tardiness,
            )
            db.add(tw)
            await db.flush()
            window_id = tw.id

            job_by_ext = {j.external_id: j for j in db_jobs}
            completion_by_job = {r.job_id: r.completion_time for r in schedule.jobs_result}
            tard_by_job = {r.job_id: r.tardiness for r in schedule.jobs_result}
            for e in schedule.entries:
                op = op_lookup.get((e.job_id, e.position_in_job))
                if op is None:
                    continue
                job = job_by_ext[e.job_id]
                setup_from_id = setup_start = setup_end = None
                setup_dur = 0
                if e.setup:
                    sf = job_by_ext.get(e.setup.from_job_id)
                    setup_from_id = sf.id if sf else None
                    setup_start, setup_end = e.setup.start_time, e.setup.end_time
                    setup_dur = e.setup.duration
                db.add(ScheduleEntry(
                    tenant_id=resolution.tenant_id, resolution_id=resolution.id,
                    operation_id=op.id, job_id=job.id, machine_id=op.machine_id,
                    window_id=window_id,
                    start_time=e.start_time, end_time=e.end_time,
                    setup_from_job_id=setup_from_id,
                    setup_start_time=setup_start, setup_end_time=setup_end,
                    setup_duration=setup_dur,
                    job_completion_time=completion_by_job.get(e.job_id),
                    job_tardiness=tard_by_job.get(e.job_id),
                ))

            # KPIs
            resolution.method_used = schedule.method_used
            resolution.total_weighted_tardiness = schedule.total_weighted_tardiness
            resolution.nb_jobs_late = schedule.nb_jobs_late
            resolution.nb_jobs_on_time = schedule.nb_jobs_on_time
            resolution.max_tardiness = schedule.max_tardiness
            resolution.machine_utilization_pct = schedule.machine_utilization_pct(machine_ids)
            resolution.total_setup_time = schedule.total_setup_time
            resolution.atcs_weighted_tardiness = schedule.atcs_twt
            resolution.improvement_vs_atcs_pct = schedule.improvement_vs_atcs_pct
            resolution.status = "completed"
            resolution.completed_at = _now()
            resolution.progress_pct = 100
            resolution.progress_detail = {"phase": 4, "label": "Termine"}
            if resolution.started_at:
                resolution.duration_seconds = round(
                    (resolution.completed_at - resolution.started_at).total_seconds(), 3
                )
            if instance:
                instance.status = "solved"
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            resolution = await db.get(Resolution, resolution_id)
            if resolution:
                resolution.status = "failed"
                resolution.error_message = str(exc)
                resolution.completed_at = _now()
                if instance:
                    instance.status = "error"
                await db.commit()


# --------------------------------------------------------------------------
# Read endpoints
# --------------------------------------------------------------------------
async def _get_resolution(tenant_id, resolution_id, db) -> Resolution:
    res = await db.get(Resolution, resolution_id)
    if res is None or res.tenant_id != tenant_id:
        raise not_found("Resolution introuvable")
    return res


def _kpis(res: Resolution) -> KPIs:
    return KPIs(
        total_weighted_tardiness=float(res.total_weighted_tardiness) if res.total_weighted_tardiness is not None else None,
        nb_jobs_late=res.nb_jobs_late, nb_jobs_on_time=res.nb_jobs_on_time,
        max_tardiness=float(res.max_tardiness) if res.max_tardiness is not None else None,
        machine_utilization_pct=float(res.machine_utilization_pct) if res.machine_utilization_pct is not None else None,
        total_setup_time=res.total_setup_time,
        atcs_weighted_tardiness=float(res.atcs_weighted_tardiness) if res.atcs_weighted_tardiness is not None else None,
        improvement_vs_atcs_pct=float(res.improvement_vs_atcs_pct) if res.improvement_vs_atcs_pct is not None else None,
    )


async def get_resolution(tenant_id, resolution_id, db) -> ResolutionStatus:
    res = await _get_resolution(tenant_id, resolution_id, db)
    has_kpi = res.status in ("completed", "partial")
    return ResolutionStatus(
        id=res.id, instance_id=res.instance_id, status=res.status,
        progress_pct=res.progress_pct, current_phase=res.current_phase,
        progress_detail=res.progress_detail, method_used=res.method_used,
        kpis=_kpis(res) if has_kpi else None,
        duration_seconds=float(res.duration_seconds) if res.duration_seconds is not None else None,
        started_at=res.started_at, completed_at=res.completed_at,
        error_message=res.error_message,
    )


async def get_gantt(
    tenant_id, resolution_id, machine_ids, t_start, t_end,
    include_setups, include_windows, db,
) -> GanttResponse:
    res = await _get_resolution(tenant_id, resolution_id, db)

    erows = await db.execute(
        select(ScheduleEntry).where(ScheduleEntry.resolution_id == resolution_id)
    )
    entries = erows.scalars().all()

    mrows = await db.execute(select(Machine).where(Machine.tenant_id == tenant_id))
    machines = {m.id: m for m in mrows.scalars().all()}
    jrows = await db.execute(select(Job).where(Job.instance_id == res.instance_id))
    jobs = {j.id: j for j in jrows.scalars().all()}
    orows = await db.execute(
        select(Operation).where(Operation.tenant_id == tenant_id)
    )
    ops = {o.id: o for o in orows.scalars().all()}
    wrows = await db.execute(
        select(TimeWindow).where(TimeWindow.resolution_id == resolution_id)
        .order_by(TimeWindow.window_index)
    )
    windows = wrows.scalars().all()
    win_index_by_id = {w.id: w.window_index for w in windows}

    gantt_entries = []
    for e in entries:
        if machine_ids and str(e.machine_id) not in machine_ids:
            continue
        if t_start is not None and e.end_time < t_start:
            continue
        if t_end is not None and e.start_time > t_end:
            continue
        job = jobs.get(e.job_id)
        machine = machines.get(e.machine_id)
        op = ops.get(e.operation_id)
        setup = None
        if include_setups and e.setup_from_job_id and e.setup_duration:
            from_job = jobs.get(e.setup_from_job_id)
            setup = SetupInfo(
                from_job_id=e.setup_from_job_id,
                from_job_external_id=from_job.external_id if from_job else "",
                start_time=e.setup_start_time or 0, end_time=e.setup_end_time or 0,
                duration=e.setup_duration,
            )
        gantt_entries.append(GanttEntry(
            job_id=e.job_id, job_external_id=job.external_id if job else "",
            job_deadline=job.deadline if job else 0,
            job_weight=float(job.weight) if job else 0.0,
            job_tardiness=float(e.job_tardiness) if e.job_tardiness is not None else None,
            job_completion_time=e.job_completion_time,
            is_late=bool(e.job_tardiness and e.job_tardiness > 0),
            machine_id=e.machine_id,
            machine_external_id=machine.external_id if machine else "",
            start_time=e.start_time, end_time=e.end_time,
            duration=e.end_time - e.start_time,
            position_in_job=op.position if op else 0,
            window_index=win_index_by_id.get(e.window_id),
            setup=setup,
        ))

    win_summaries = []
    if include_windows:
        win_summaries = [
            WindowSummary(
                window_index=w.window_index, t_start=w.t_start, t_end=w.t_end,
                nb_jobs=w.nb_jobs, status=w.status, method_used=w.method_used,
            )
            for w in windows
        ]

    return GanttResponse(
        resolution_id=res.id, horizon=max((e.end_time for e in entries), default=0),
        kpis=_kpis(res),
        machines=[
            MachineSummary(id=m.id, external_id=m.external_id, name=m.name)
            for m in machines.values()
        ],
        windows=win_summaries, entries=gantt_entries,
    )


async def get_job_in_resolution(tenant_id, resolution_id, job_id, db) -> JobDetailInResolution:
    res = await _get_resolution(tenant_id, resolution_id, db)
    job = await db.get(Job, job_id)
    if job is None or job.instance_id != res.instance_id:
        raise not_found("Job introuvable dans cette resolution")

    erows = await db.execute(
        select(ScheduleEntry).where(
            ScheduleEntry.resolution_id == resolution_id, ScheduleEntry.job_id == job_id
        )
    )
    entries = erows.scalars().all()
    mrows = await db.execute(select(Machine).where(Machine.tenant_id == tenant_id))
    mext = {m.id: m.external_id for m in mrows.scalars().all()}
    orows = await db.execute(select(Operation).where(Operation.job_id == job_id))
    ops = {o.id: o for o in orows.scalars().all()}
    jrows = await db.execute(select(Job).where(Job.instance_id == res.instance_id))
    jext = {j.id: j.external_id for j in jrows.scalars().all()}

    op_schedule = []
    completion = None
    tardiness = None
    window_index = None
    for e in sorted(entries, key=lambda x: x.start_time):
        op = ops.get(e.operation_id)
        op_schedule.append(OperationInSchedule(
            position=op.position if op else 0,
            machine_external_id=mext.get(e.machine_id, ""),
            start_time=e.start_time, end_time=e.end_time,
            duration=e.end_time - e.start_time,
            setup_from_job=jext.get(e.setup_from_job_id) if e.setup_from_job_id else None,
            setup_duration=e.setup_duration,
        ))
        if e.job_completion_time is not None:
            completion = e.job_completion_time
        if e.job_tardiness is not None:
            tardiness = float(e.job_tardiness)

    win = await db.execute(
        select(TimeWindow).where(TimeWindow.resolution_id == resolution_id)
        .order_by(TimeWindow.window_index).limit(1)
    )
    w = win.scalar_one_or_none()
    if w:
        window_index, window_status = w.window_index, w.status
    else:
        window_status = None

    is_late = bool(tardiness and tardiness > 0)
    return JobDetailInResolution(
        job_id=job.id, external_id=job.external_id, deadline=job.deadline,
        weight=float(job.weight), completion_time=completion, tardiness=tardiness,
        is_late=is_late,
        weighted_tardiness=round(float(job.weight) * tardiness, 4) if tardiness is not None else None,
        window_index=window_index, window_status=window_status, operations=op_schedule,
    )


async def delete_resolution(tenant_id, resolution_id, db) -> None:
    res = await _get_resolution(tenant_id, resolution_id, db)
    await db.delete(res)
    await db.commit()
    return None


async def cancel_resolution(tenant_id, resolution_id, db) -> ResolutionStatus:
    res = await _get_resolution(tenant_id, resolution_id, db)
    if res.status in ("pending", "running"):
        res.status = "cancelled"
        res.completed_at = _now()
        await db.commit()
        await db.refresh(res)
    return await get_resolution(tenant_id, resolution_id, db)
