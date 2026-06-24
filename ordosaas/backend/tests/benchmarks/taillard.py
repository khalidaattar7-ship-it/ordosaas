"""
Generateur d'instances Job-Shop classiques (Taillard, 1993).

Pas de setups sequence-dependants. Chaque job passe sur chaque machine dans
un ordre aleatoire ; durees uniformes [1, 99].
"""
import random

from scheduling.models.job import Job, Operation, ProblemInstance


def generate_taillard_instance(nb_jobs: int, nb_machines: int, seed: int = 42) -> ProblemInstance:
    """Genere une instance Job-Shop de type Taillard.

    Args:
        nb_jobs: nombre de jobs.
        nb_machines: nombre de machines.
        seed: graine pour la reproductibilite.

    Returns:
        ProblemInstance avec setup_times vide et un ordre machine aleatoire
        par job (chaque machine visitee exactement une fois).
    """
    rng = random.Random(seed)
    machines = [f"M{i + 1}" for i in range(nb_machines)]

    jobs = []
    total_processing = 0
    for j in range(nb_jobs):
        machine_order = machines[:]
        rng.shuffle(machine_order)
        ops = []
        for pos, machine in enumerate(machine_order, start=1):
            duration = rng.randint(1, 99)
            total_processing += duration
            ops.append(Operation(job_id=f"J{j + 1}", machine_id=machine, duration=duration, position=pos))
        jobs.append(Job(id=f"J{j + 1}", operations=ops, deadline=0, weight=round(rng.uniform(1.0, 10.0), 2)))

    # Deadlines moderement serrees autour de la charge moyenne par job.
    avg_proc = total_processing / nb_jobs if nb_jobs else 1
    for job in jobs:
        job.deadline = max(1, int(avg_proc * rng.uniform(0.8, 1.6)))

    return ProblemInstance(jobs=jobs, machines=machines, setup_times={}, wr=nb_machines)
