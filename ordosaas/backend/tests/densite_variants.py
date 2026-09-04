"""
Variantes de densite de l'instance d'exemple a 10 jobs.

Livrable 2 de la Discussion 2. Sert a mesurer comment la densite du planning
initial influence l'ampleur de la zone d'impact et le declenchement du garde-fou
de repli — la question produit restee ouverte en fin de Discussion 1.

## Pourquoi ce levier, et pas ceux qu'on essaie d'abord

Deux leviers plus evidents ont ete mesures et **ne fonctionnent pas** sur cette
instance :

- **Desserrer les deadlines** (x1.5, x2.5, x4) : l'utilisation machine reste a
  68-70 % dans tous les cas. Les deadlines pilotent le retard, pas l'occupation :
  CP-SAT compacte de la meme facon, il place simplement les memes operations avec
  moins de retard.
- **Raccourcir les durees** (x0.7, x0.5, x0.3) : l'horizon se contracte dans la
  meme proportion, donc la densite ne bouge pas (elle remonte meme a 80 % a x0.5).

Dans les deux cas, **M1 reste saturee a 100 %** (aucun temps mort entre deux
operations consecutives). C'est une propriete structurelle de l'instance : la
machine goulot porte une charge de 509 unites que CP-SAT tasse au plus serre, et
aucun reglage de deadline ou de duree ne l'aere.

## Le levier retenu : l'etirement du planning

On etire le planning optimal d'un facteur `s >= 1` : toutes les dates de debut
(operations **et** setups) sont multipliees par `s`, les durees restent
inchangees. Le temps mort apparait donc entre les operations, proportionnellement.

Ce levier a trois proprietes qui le rendent exploitable :

1. **Il modelise directement l'un des deux termes de la question produit** — «
   conserver de la marge dans le planning initial ». Ce n'est pas un artefact de
   mesure : c'est exactement le planning qu'obtiendrait un atelier qui garde
   volontairement du mou.
2. **Il conserve les 10 jobs.** Reduire le nombre de jobs aere aussi le planning
   (mesure : 39 % d'utilisation a 4 jobs), mais change le denominateur du ratio
   « part des jobs futurs touches » sur lequel porte le garde-fou — les variantes
   ne seraient plus comparables entre elles. L'etirement evite ce biais.
3. **Il preserve la validite par construction**, ce qui se demontre :
   - precedence `a -> b` d'un job : `da <= b.start - a.start` dans l'original,
     donc `da <= (b.start - a.start) * s` pour tout `s >= 1` ;
   - NoOverlap machine et placement des setups : meme argument, chaque ecart etant
     multiplie par `s` alors que les durees restent constantes.

Les deadlines sont etirees du meme facteur, sans quoi la variante detendue serait
un planning absurde ou tous les jobs sont massivement en retard.
"""
import os
from dataclasses import replace

from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.schedule import Schedule
from scheduling.solvers.cpsat_solver import CPSATSolver
from tests.validate_example import (
    FIXTURES_DIR,
    build_jobs,
    parse_jobs_csv,
    parse_ops_csv,
    parse_setups_csv,
)

# Les trois variantes retenues, avec leur facteur d'etirement.
# Les taux d'utilisation indiques sont ceux mesures sur l'instance d'exemple.
DENSITES = {
    "dense": 1.0,      # ~69 % d'utilisation — le planning CP-SAT tel quel, M1 saturee
    "moderee": 1.4,    # ~51 % d'utilisation — du temps mort sur les trois machines
    "detendue": 2.0,   # ~36 % d'utilisation — marge large
}


def charge_instance_exemple() -> ProblemInstance:
    """L'instance d'exemple du depot : 10 jobs, 3 machines, WR = 2."""
    jobs_rows = parse_jobs_csv(os.path.join(FIXTURES_DIR, "jobs.csv"))
    ops_rows = parse_ops_csv(os.path.join(FIXTURES_DIR, "operations.csv"))
    setup_rows = parse_setups_csv(os.path.join(FIXTURES_DIR, "setups.csv"))
    return ProblemInstance(
        jobs=build_jobs(jobs_rows, ops_rows),
        machines=sorted({o["machine_id"] for o in ops_rows}),
        setup_times={
            (r["from_job"], r["to_job"], r["machine_id"]): r["duration"]
            for r in setup_rows
        },
        wr=2,
    )


def etire(schedule, instance, facteur: float):
    """Etire un planning et son instance d'un facteur `s >= 1`.

    Multiplie toutes les dates de debut par `facteur` en gardant les durees, ce qui
    insere du temps mort proportionnel entre les operations. Les deadlines suivent
    le meme facteur.

    Returns:
        (Schedule etire, ProblemInstance aux deadlines etirees)
    """
    if facteur < 1:
        raise ValueError(f"le facteur d'etirement doit etre >= 1, recu {facteur}")

    entrees = []
    for e in schedule.entries:
        debut = int(round(e.start_time * facteur))
        setup = None
        if e.setup and e.setup.duration > 0:
            s_debut = int(round(e.setup.start_time * facteur))
            setup = replace(e.setup, start_time=s_debut,
                            end_time=s_debut + e.setup.duration)
        entrees.append(replace(e, start_time=debut, end_time=debut + e.duration,
                               setup=setup))

    jobs = [
        Job(id=j.id, operations=j.operations,
            deadline=int(round(j.deadline * facteur)), weight=j.weight)
        for j in instance.jobs
    ]
    etiree = ProblemInstance(jobs=jobs, machines=list(instance.machines),
                             setup_times=instance.setup_times, wr=instance.wr)
    planning = Schedule(entries=entrees, method_used=schedule.method_used,
                        solver_status=schedule.solver_status)
    planning.compute_kpis(jobs)
    return planning, etiree


def construit_variantes(timeout_seconds: int = 30) -> dict:
    """Les trois variantes de densite, resolues puis etirees.

    Returns:
        {nom: (Schedule, ProblemInstance)}
    """
    base = charge_instance_exemple()
    optimal = CPSATSolver(timeout_seconds=timeout_seconds).solve(base)
    if optimal is None:
        raise RuntimeError("le solveur initial n'a pas trouve de solution")
    return {nom: etire(optimal, base, facteur) for nom, facteur in DENSITES.items()}


# --------------------------------------------------------------------------
# Mesures de densite
# --------------------------------------------------------------------------
def _occupation_debut(entry) -> int:
    if entry.setup and entry.setup.duration > 0:
        return min(entry.start_time, entry.setup.start_time)
    return entry.start_time


def mesure_densite(schedule, instance) -> dict:
    """Utilisation machine et temps mort d'un planning.

    `temps_mort` ne compte que les trous INTERNES, entre deux occupations
    consecutives d'une machine — c'est lui qui absorbe un retard. Le temps avant la
    premiere operation et apres la derniere n'absorbe rien.
    """
    par_machine = {}
    for entry in schedule.entries:
        par_machine.setdefault(entry.machine_id, []).append(
            (_occupation_debut(entry), entry.end_time)
        )

    horizon = schedule.horizon
    occupation, temps_mort, par_machine_mort = 0, 0, {}
    for machine_id in instance.machines:
        intervalles = sorted(par_machine.get(machine_id, []))
        if not intervalles:
            par_machine_mort[machine_id] = 0
            continue
        occupation += sum(fin - debut for debut, fin in intervalles)
        trous = sum(
            max(0, intervalles[k + 1][0] - intervalles[k][1])
            for k in range(len(intervalles) - 1)
        )
        par_machine_mort[machine_id] = trous
        temps_mort += trous

    denominateur = horizon * len(instance.machines)
    return {
        "horizon": horizon,
        "utilisation_pct": round(100 * occupation / denominateur, 1) if denominateur else 0.0,
        "temps_mort": temps_mort,
        "temps_mort_par_machine": par_machine_mort,
        "twt": schedule.total_weighted_tardiness,
        "nb_jobs_late": schedule.nb_jobs_late,
    }


# --------------------------------------------------------------------------
# Perturbations appliquees a chaque variante
# --------------------------------------------------------------------------
def premiere_entree_future(schedule, t_now: int, machine_id: str = None):
    """Premiere entree demarrant apres T_now, eventuellement sur une machine donnee."""
    candidates = [
        e for e in schedule.entries
        if e.start_time > t_now and (machine_id is None or e.machine_id == machine_id)
    ]
    return min(candidates, key=lambda e: e.start_time) if candidates else None


def job_urgent_type(instance, t_now: int, duree: int = 25):
    """Un job urgent standard : deux operations, deadline serree.

    Les durees sont ABSOLUES et non etirees : une commande urgente reelle ne
    change pas de taille selon la marge que le planificateur s'est gardee.
    """
    machines = instance.machines[:2]
    operations = [
        Operation("URGENT", machines[0], duree, 1),
        Operation("URGENT", machines[1], duree, 2),
    ]
    return dict(job_id="URGENT", operations=operations,
                deadline=t_now + 4 * duree, weight=10.0)
