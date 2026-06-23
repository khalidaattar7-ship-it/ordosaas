"""Instances business logic, including the critical CSV import."""
import csv
import io

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common import UserSummary, paginate_meta
from app.errors import bad_request, conflict, not_found
from app.instances.schemas import (
    AddJobRequest,
    ImportResponse,
    InstanceListResponse,
    InstanceResponse,
    JobCSVRow,
    JobListResponse,
    JobResponse,
    OperationCSVRow,
    PatchJobRequest,
    SetupCSVRow,
    ValidationWarning,
)
from app.models.instance import ProblemInstance
from app.models.job import Job
from app.models.machine import Machine
from app.models.operation import Operation
from app.models.resolution import Resolution
from app.models.setup_time import SetupTime
from app.models.user import User


def _parse_csv(content: str, label: str) -> list[dict]:
    if not content or not content.strip():
        return []
    try:
        reader = csv.DictReader(io.StringIO(content))
        return [
            {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            for row in reader
        ]
    except Exception as exc:  # noqa: BLE001
        raise bad_request(f"Impossible de parser le CSV {label}: {exc}")


def _require_columns(rows: list[dict], required: set[str], label: str):
    if not rows:
        raise bad_request(f"Le fichier {label} est vide")
    missing = required - set(rows[0].keys())
    if missing:
        raise bad_request(
            f"Colonnes manquantes dans {label}: {', '.join(sorted(missing))}"
        )


async def import_instance(
    name, description, jobs_csv, operations_csv, setups_csv,
    tenant_id, user_id, db: AsyncSession,
) -> ImportResponse:
    warnings: list[ValidationWarning] = []

    # 1-3. Parse + validate required columns
    job_rows = _parse_csv(jobs_csv, "jobs")
    op_rows = _parse_csv(operations_csv, "operations")
    setup_rows = _parse_csv(setups_csv, "setups") if setups_csv else []
    _require_columns(job_rows, {"job_id", "deadline", "weight"}, "jobs")
    _require_columns(op_rows, {"job_id", "machine_id", "duration", "position"}, "operations")
    if setup_rows:
        _require_columns(setup_rows, {"from_job", "to_job", "machine_id", "duration"}, "setups")

    # Typed validation of jobs
    jobs: dict[str, JobCSVRow] = {}
    for r in job_rows:
        try:
            job = JobCSVRow(
                job_id=r["job_id"], deadline=int(r["deadline"]), weight=float(r["weight"])
            )
        except (ValueError, KeyError) as exc:
            raise bad_request(f"Ligne job invalide ({r}): {exc}")
        if job.job_id in jobs:
            raise bad_request(f"Job en double dans jobs.csv: {job.job_id}")
        jobs[job.job_id] = job

    # Load tenant machines by external_id
    mrows = await db.execute(select(Machine).where(Machine.tenant_id == tenant_id))
    machines_by_ext = {m.external_id: m for m in mrows.scalars().all()}

    # Validate operations
    operations: list[OperationCSVRow] = []
    seen_job_machine: set[tuple[str, str]] = set()
    used_machines: set[str] = set()
    jobs_with_ops: set[str] = set()
    for r in op_rows:
        try:
            op = OperationCSVRow(
                job_id=r["job_id"], machine_id=r["machine_id"],
                duration=int(r["duration"]), position=int(r["position"]),
            )
        except (ValueError, KeyError) as exc:
            raise bad_request(f"Ligne operation invalide ({r}): {exc}")
        if op.job_id not in jobs:
            raise bad_request(f"Operation refere un job inconnu: {op.job_id}")
        if op.machine_id not in machines_by_ext:
            raise bad_request(f"Machine inconnue dans le tenant: {op.machine_id}")
        key = (op.job_id, op.machine_id)
        if key in seen_job_machine:
            raise bad_request(f"Doublon (job, machine) dans operations: {key}")
        seen_job_machine.add(key)
        used_machines.add(op.machine_id)
        jobs_with_ops.add(op.job_id)
        operations.append(op)

    orphan_jobs = [j for j in jobs if j not in jobs_with_ops]
    if orphan_jobs:
        raise bad_request(
            "Certains jobs n'ont aucune operation", detail={"jobs": orphan_jobs}
        )

    # Validate setups (optional, non-blocking warnings)
    setups: list[SetupCSVRow] = []
    seen_setup: set[tuple[str, str, str]] = set()
    for r in setup_rows:
        try:
            s = SetupCSVRow(
                from_job=r["from_job"], to_job=r["to_job"],
                machine_id=r["machine_id"], duration=int(r["duration"]),
            )
        except (ValueError, KeyError) as exc:
            raise bad_request(f"Ligne setup invalide ({r}): {exc}")
        if s.from_job not in jobs or s.to_job not in jobs:
            warnings.append(ValidationWarning(
                code="setup_unknown_job",
                message=f"Setup ignore: job inconnu ({s.from_job}->{s.to_job})",
                affected_jobs=[s.from_job, s.to_job],
            ))
            continue
        if s.machine_id not in machines_by_ext:
            warnings.append(ValidationWarning(
                code="setup_unknown_machine",
                message=f"Setup ignore: machine inconnue ({s.machine_id})",
                affected_jobs=[s.from_job, s.to_job],
            ))
            continue
        key = (s.from_job, s.to_job, s.machine_id)
        if key in seen_setup:
            raise bad_request(f"Doublon de setup: {key}")
        seen_setup.add(key)
        setups.append(s)

    unused = sorted(set(machines_by_ext) - used_machines)
    if unused:
        warnings.append(ValidationWarning(
            code="unused_machines",
            message="Des machines ne sont utilisees par aucune operation",
            affected_jobs=[],
        ))

    # Persist in a single transaction
    instance = ProblemInstance(
        tenant_id=tenant_id, created_by=user_id, name=name, description=description,
        nb_jobs=len(jobs), nb_machines=len(used_machines),
        nb_operations=len(operations), nb_setups=len(setups),
        status="draft", import_source="csv",
        raw_jobs_csv=jobs_csv, raw_operations_csv=operations_csv, raw_setups_csv=setups_csv,
    )
    db.add(instance)
    await db.flush()

    job_models: dict[str, Job] = {}
    for ext_id, j in jobs.items():
        jm = Job(tenant_id=tenant_id, instance_id=instance.id, external_id=ext_id,
                 deadline=j.deadline, weight=j.weight)
        db.add(jm)
        job_models[ext_id] = jm
    await db.flush()

    for op in operations:
        db.add(Operation(
            tenant_id=tenant_id, job_id=job_models[op.job_id].id,
            machine_id=machines_by_ext[op.machine_id].id,
            position=op.position, duration=op.duration,
        ))
    for s in setups:
        db.add(SetupTime(
            tenant_id=tenant_id, instance_id=instance.id,
            from_job_id=job_models[s.from_job].id, to_job_id=job_models[s.to_job].id,
            machine_id=machines_by_ext[s.machine_id].id, duration=s.duration,
        ))

    await db.commit()
    await db.refresh(instance)
    return ImportResponse(
        id=instance.id, name=instance.name, nb_jobs=instance.nb_jobs,
        nb_machines=instance.nb_machines, nb_operations=instance.nb_operations,
        nb_setups=instance.nb_setups, status=instance.status,
        validation_warnings=warnings, created_at=instance.created_at,
    )


async def _instance_response(inst: ProblemInstance, db) -> InstanceResponse:
    nb_res = await db.scalar(
        select(func.count()).select_from(Resolution).where(Resolution.instance_id == inst.id)
    )
    best = await db.execute(
        select(Resolution.id, Resolution.total_weighted_tardiness)
        .where(Resolution.instance_id == inst.id, Resolution.status == "completed")
        .order_by(Resolution.total_weighted_tardiness.asc()).limit(1)
    )
    best_row = best.first()
    creator = await db.get(User, inst.created_by)
    return InstanceResponse(
        id=inst.id, name=inst.name, description=inst.description,
        nb_jobs=inst.nb_jobs, nb_machines=inst.nb_machines,
        nb_operations=inst.nb_operations, nb_setups=inst.nb_setups,
        status=inst.status, import_source=inst.import_source,
        nb_resolutions=nb_res or 0,
        best_resolution_id=best_row[0] if best_row else None,
        best_weighted_tardiness=float(best_row[1]) if best_row and best_row[1] is not None else None,
        created_by=UserSummary(
            id=creator.id, email=creator.email,
            first_name=creator.first_name, last_name=creator.last_name,
        ) if creator else None,
        created_at=inst.created_at, updated_at=inst.updated_at,
    )


async def list_instances(tenant_id, page, per_page, db) -> InstanceListResponse:
    total = await db.scalar(
        select(func.count()).select_from(ProblemInstance)
        .where(ProblemInstance.tenant_id == tenant_id)
    )
    rows = await db.execute(
        select(ProblemInstance).where(ProblemInstance.tenant_id == tenant_id)
        .order_by(ProblemInstance.created_at.desc())
        .offset((page - 1) * per_page).limit(per_page)
    )
    data = [await _instance_response(i, db) for i in rows.scalars().all()]
    return InstanceListResponse(data=data, pagination=paginate_meta(page, per_page, total or 0))


async def _get_instance(tenant_id, instance_id, db) -> ProblemInstance:
    inst = await db.get(ProblemInstance, instance_id)
    if inst is None or inst.tenant_id != tenant_id:
        raise not_found("Instance introuvable")
    return inst


async def get_instance(tenant_id, instance_id, db) -> InstanceResponse:
    inst = await _get_instance(tenant_id, instance_id, db)
    return await _instance_response(inst, db)


async def list_jobs(tenant_id, instance_id, page, per_page, db) -> JobListResponse:
    await _get_instance(tenant_id, instance_id, db)
    total = await db.scalar(
        select(func.count()).select_from(Job).where(Job.instance_id == instance_id)
    )
    rows = await db.execute(
        select(Job).where(Job.instance_id == instance_id)
        .options(selectinload(Job.operations))
        .order_by(Job.external_id).offset((page - 1) * per_page).limit(per_page)
    )
    jobs = rows.scalars().all()
    mrows = await db.execute(select(Machine).where(Machine.tenant_id == tenant_id))
    mext = {m.id: m.external_id for m in mrows.scalars().all()}
    data = [
        JobResponse(
            id=j.id, external_id=j.external_id, deadline=j.deadline, weight=float(j.weight),
            nb_operations=len(j.operations),
            machines=[mext.get(o.machine_id, "") for o in j.operations],
        )
        for j in jobs
    ]
    return JobListResponse(data=data, pagination=paginate_meta(page, per_page, total or 0))


async def _get_job(tenant_id, instance_id, job_id, db) -> Job:
    job = await db.get(Job, job_id)
    if job is None or job.tenant_id != tenant_id or job.instance_id != instance_id:
        raise not_found("Job introuvable")
    return job


async def patch_job(tenant_id, instance_id, job_id, data: PatchJobRequest, db) -> JobResponse:
    job = await _get_job(tenant_id, instance_id, job_id, db)
    if data.deadline is not None:
        job.deadline = data.deadline
    if data.weight is not None:
        job.weight = data.weight
    await db.commit()
    await db.refresh(job)
    ops = (await db.execute(select(Operation).where(Operation.job_id == job.id))).scalars().all()
    return JobResponse(
        id=job.id, external_id=job.external_id, deadline=job.deadline,
        weight=float(job.weight), nb_operations=len(ops), machines=[],
    )


async def add_job(tenant_id, instance_id, data: AddJobRequest, db) -> JobResponse:
    inst = await _get_instance(tenant_id, instance_id, db)
    dup = await db.execute(
        select(Job).where(Job.instance_id == instance_id, Job.external_id == data.external_id)
    )
    if dup.scalar_one_or_none():
        raise conflict(f"Un job '{data.external_id}' existe deja dans cette instance")
    job = Job(tenant_id=tenant_id, instance_id=instance_id, external_id=data.external_id,
              deadline=data.deadline, weight=data.weight)
    db.add(job)
    await db.flush()
    for op in data.operations:
        machine = await db.get(Machine, op.machine_id)
        if machine is None or machine.tenant_id != tenant_id:
            raise bad_request(f"Machine inconnue: {op.machine_id}")
        db.add(Operation(tenant_id=tenant_id, job_id=job.id, machine_id=op.machine_id,
                         position=op.position, duration=op.duration))
    inst.nb_jobs += 1
    inst.nb_operations += len(data.operations)
    await db.commit()
    await db.refresh(job)
    return JobResponse(
        id=job.id, external_id=job.external_id, deadline=job.deadline,
        weight=float(job.weight), nb_operations=len(data.operations), machines=[],
    )


async def delete_job(tenant_id, instance_id, job_id, db) -> None:
    job = await _get_job(tenant_id, instance_id, job_id, db)
    inst = await _get_instance(tenant_id, instance_id, db)
    nb_ops = await db.scalar(
        select(func.count()).select_from(Operation).where(Operation.job_id == job.id)
    )
    await db.delete(job)
    inst.nb_jobs = max(0, inst.nb_jobs - 1)
    inst.nb_operations = max(0, inst.nb_operations - (nb_ops or 0))
    await db.commit()
    return None


async def delete_instance(tenant_id, instance_id, db) -> None:
    inst = await _get_instance(tenant_id, instance_id, db)
    await db.delete(inst)
    await db.commit()
    return None
