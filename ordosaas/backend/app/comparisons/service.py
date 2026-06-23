"""Comparisons business logic."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.comparisons.schemas import (
    ComparisonResponse,
    DeltaSummary,
    JobDelta,
    ResolutionSummary,
)
from app.errors import bad_request, not_found
from app.models.comparison import SolutionComparison
from app.models.job import Job
from app.models.resolution import Resolution
from app.models.schedule_entry import ScheduleEntry


def _f(v):
    return float(v) if v is not None else None


def _summary(res: Resolution) -> ResolutionSummary:
    return ResolutionSummary(
        id=res.id, method_used=res.method_used,
        total_weighted_tardiness=_f(res.total_weighted_tardiness),
        nb_jobs_late=res.nb_jobs_late,
        machine_utilization_pct=_f(res.machine_utilization_pct),
        total_setup_time=res.total_setup_time,
    )


async def _job_tardiness_map(db, resolution_id):
    rows = await db.execute(
        select(Job.external_id, ScheduleEntry.job_tardiness)
        .join(ScheduleEntry, ScheduleEntry.job_id == Job.id)
        .where(ScheduleEntry.resolution_id == resolution_id)
    )
    out = {}
    for ext, tard in rows.all():
        if tard is not None:
            out[ext] = float(tard)
    return out


async def compare(tenant_id, user_id, res_a_id, res_b_id, db: AsyncSession) -> ComparisonResponse:
    res_a = await db.get(Resolution, res_a_id)
    res_b = await db.get(Resolution, res_b_id)
    if res_a is None or res_a.tenant_id != tenant_id:
        raise not_found("Resolution A introuvable")
    if res_b is None or res_b.tenant_id != tenant_id:
        raise not_found("Resolution B introuvable")
    if res_a.status != "completed" or res_b.status != "completed":
        raise bad_request("Les deux resolutions doivent etre completees")

    twt_a = _f(res_a.total_weighted_tardiness) or 0.0
    twt_b = _f(res_b.total_weighted_tardiness) or 0.0
    delta_twt = round(twt_b - twt_a, 4)
    delta_late = (res_b.nb_jobs_late or 0) - (res_a.nb_jobs_late or 0)
    util_a = _f(res_a.machine_utilization_pct) or 0.0
    util_b = _f(res_b.machine_utilization_pct) or 0.0
    delta_util = round(util_b - util_a, 2)
    delta_setup = (res_b.total_setup_time or 0) - (res_a.total_setup_time or 0)

    # B is better when its weighted tardiness is lower (delta < 0).
    winner = "B" if delta_twt < 0 else "A"

    tard_a = await _job_tardiness_map(db, res_a_id)
    tard_b = await _job_tardiness_map(db, res_b_id)
    changed = []
    for ext in sorted(set(tard_a) | set(tard_b)):
        ta = tard_a.get(ext)
        tb = tard_b.get(ext)
        if ta != tb:
            changed.append(JobDelta(
                external_id=ext, tardiness_a=ta, tardiness_b=tb,
                delta=round((tb or 0) - (ta or 0), 4),
            ))

    comparison = SolutionComparison(
        tenant_id=tenant_id, created_by=user_id,
        resolution_a_id=res_a_id, resolution_b_id=res_b_id,
        delta_weighted_tardiness=delta_twt, delta_jobs_late=delta_late,
        delta_machine_utilization=delta_util, winner=winner,
    )
    db.add(comparison)
    await db.commit()
    await db.refresh(comparison)

    return ComparisonResponse(
        id=comparison.id, resolution_a=_summary(res_a), resolution_b=_summary(res_b),
        delta=DeltaSummary(
            delta_weighted_tardiness=delta_twt, delta_jobs_late=delta_late,
            delta_machine_utilization=delta_util, delta_setup_time=delta_setup,
        ),
        winner=winner, changed_jobs=changed, created_at=comparison.created_at,
    )
