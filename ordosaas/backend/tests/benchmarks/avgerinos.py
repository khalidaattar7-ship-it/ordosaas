"""
Generateur d'instances de test selon le protocole Avgerinos et al. (2023).

- Taille : |M| in {2, 5, 10}, |J| in {5|M|, 10|M|}
- Serrage delais tau in {0.5, 0.8}, plage R = 0.8
- Setup ratio alpha in [0.1, 0.5] ou [0.5, 1.0]
- WR in {ceil(|M|/2), |M|}
- Generateur deterministe avec seed
"""
import math
import random

from scheduling.models.job import Job, Operation, ProblemInstance


def generate_avgerinos_instance(
    nb_machines: int,
    nb_jobs: int,
    tau: float = 0.5,
    R: float = 0.8,
    alpha_range: tuple = (0.1, 0.5),
    wr_ratio: str = "half",  # 'half' or 'full'
    seed: int = 42,
) -> ProblemInstance:
    """Genere une instance selon le protocole Avgerinos et al."""
    rng = random.Random(seed)

    machines = [f"M{i + 1}" for i in range(nb_machines)]
    wr = math.ceil(nb_machines / 2) if wr_ratio == "half" else nb_machines

    jobs = []
    total_processing = 0
    for j in range(nb_jobs):
        ops = []
        for m_idx, machine in enumerate(machines):
            duration = rng.randint(1, 100)
            total_processing += duration
            ops.append(Operation(
                job_id=f"J{j + 1}", machine_id=machine,
                duration=duration, position=m_idx + 1,
            ))
        jobs.append(Job(
            id=f"J{j + 1}", operations=ops, deadline=0,
            weight=round(rng.uniform(1.0, 10.0), 2),
        ))

    avg_proc = total_processing / nb_jobs if nb_jobs > 0 else 1
    for job in jobs:
        lower = avg_proc * (1 - tau) * (1 - R / 2)
        upper = avg_proc * (1 - tau) * (1 + R / 2)
        job.deadline = max(1, int(rng.uniform(lower, upper) * nb_machines))

    setup_times = {}
    for m in machines:
        for fi in range(nb_jobs):
            for ti in range(nb_jobs):
                if fi == ti:
                    continue
                from_job = f"J{fi + 1}"
                to_job = f"J{ti + 1}"
                to_op = next(op for op in jobs[ti].operations if op.machine_id == m)
                alpha = rng.uniform(*alpha_range)
                s_dur = max(0, int(alpha * to_op.duration))
                if s_dur > 0:
                    setup_times[(from_job, to_job, m)] = s_dur

    return ProblemInstance(
        jobs=jobs, machines=machines, setup_times=setup_times, wr=wr
    )
