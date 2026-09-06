"""
Variantes de densite de l'instance d'exemple a 10 jobs.

Livrable 2 de la Discussion 2. Sert a mesurer comment la densite du planning
initial influence l'ampleur de la zone d'impact et le declenchement du garde-fou
de repli — la question produit restee ouverte en fin de Discussion 1.

## Pourquoi ce levier, et pas ceux qu'on essaie d'abord

Deux leviers plus evidents ont ete mesures et **ne fonctionnent pas** sur cette
instance. Mesures refaites le 2026-09-06 avec le solveur CORRIGE (post-H8/H9), les
mesures d'origine datant d'un solveur qui ne payait aucun setup.

**Levier 1 — desserrer les deadlines** (durees inchangees) :

    deadlines x1.0   util 88.3 %   temps mort  45   (M1:0 M2:43 M3:2)
    deadlines x1.5   util 85.2 %   temps mort  71   (M1:0 M2:41 M3:30)
    deadlines x2.5   util 85.8 %   temps mort   3   (M1:0 M2:2  M3:1)
    deadlines x4.0   util 73.2 %   temps mort  16   (M1:0 M2:15 M3:1)

L'utilisation ne descend qu'a 73 % en desserrant les deadlines d'un facteur QUATRE, et
le temps mort interne reste derisoire — il DIMINUE meme a x2.5. Les deadlines pilotent
le retard, pas l'occupation : CP-SAT place les memes operations avec moins de retard.

**Levier 2 — reduire les durees** (deadlines inchangees) :

    durees x1.0   util 88.3 %   temps mort 45   (M1:0 M2:43 M3:2)
    durees x0.7   util 88.2 %   temps mort 45   (M1:0 M2:24 M3:21)
    durees x0.5   util 77.6 %   temps mort  7   (M1:0 M2:2  M3:5)
    durees x0.3   util 66.4 %   temps mort  0   (M1:0 M2:0  M3:0)

L'horizon se contracte dans la meme proportion que les durees, donc la densite bouge
peu — et le temps mort tombe a ZERO a x0.3, soit l'inverse de l'effet recherche.

**Dans les huit configurations mesurees, M1 n'a AUCUN temps mort.** C'est une propriete
structurelle de l'instance : la machine goulot est saturee, et aucun reglage de deadline
ou de duree ne l'aere. La correction de H8/H9 a renforce ce constat plutot que de
l'infirmer, les setups occupant desormais du temps machine reel.

**Un troisieme levier, ecarte pour une autre raison** — reduire le nombre de jobs aere
bien le planning (39 % d'utilisation a 4 jobs, mesure avant correction), mais change le
denominateur du ratio "part des jobs futurs touches" sur lequel porte le garde-fou : les
variantes ne seraient plus comparables entre elles.

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
   - NoOverlap machine : meme argument, chaque ecart etant multiplie par `s` alors
     que les durees restent constantes ;
   - setups : le nouveau debut vaut `setup_start + (s - 1) * op_start`, qui domine
     la fin de l'operation precedente des lors que `op_start >= prev_start` — vrai
     par construction puisque l'une precede l'autre.

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
# Facteurs calibres le 2026-09-06, apres la correction de H8/H9.
#
# `dense` reste a 1.0 DELIBEREMENT : c'est le planning que CP-SAT produit reellement,
# et c'est lui que la question produit met en balance avec l'option "garder de la
# marge". Le ramener artificiellement a 69 % pour retrouver le chiffre d'avant
# correction reviendrait a retirer de la comparaison le cas qu'elle existe pour
# eclairer. Les setups occupant desormais du temps machine reel, ce planning est
# simplement plus dense qu'avant : 88 % contre 69 %.
#
# `moderee` et `detendue` sont recalibrees sur les cibles d'origine (~51 % et ~36 %),
# ce qui rend ces deux variantes directement comparables a la premiere version de la
# matrice. La plage couverte (88 -> 36 %, soit 53 points) est plus large que celle
# d'origine (69 -> 36 %, soit 32 points).
#
# L'ecart entre dense et moderee (36 points) est plus grand qu'entre moderee et
# detendue (17 points) : la progression n'est pas reguliere, consequence de garder
# dense sur le planning reel plutot que sur une cible choisie.
DENSITES = {
    "dense": 1.0,      # 88.3 % d'utilisation — le planning CP-SAT reel, non etire
    "moderee": 1.7,    # 52.4 % — cible d'origine ~51 %
    "detendue": 2.5,   # 35.7 % — cible d'origine ~36 %
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
            # Le setup suit son operation au lieu d'etre etire independamment :
            # l'ecart d'origine entre la fin du setup et le debut de l'operation est
            # PRESERVE, et toute la marge ajoutee se place AVANT le setup — la ou
            # elle a un sens, la machine attendant avant de se preparer.
            #
            # Etirer la date de debut du setup, comme le faisait la premiere version,
            # detachait le setup de son operation et creusait un ecart vide croissant.
            # Cet ecart etait compte comme de l'occupation machine et faussait la
            # mesure de densite : 862 unites fictives a s = 3.0, soit une utilisation
            # bloquee a 43 % au lieu des ~30 % reels. Invisible avant la correction de
            # H8/H9, puisque aucun planning ne portait alors de setup.
            ecart = e.start_time - e.setup.end_time
            s_fin = debut - ecart
            setup = replace(e.setup, start_time=s_fin - e.setup.duration,
                            end_time=s_fin)
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

    Le planning de depart est resolu avec la configuration DETERMINISTE du fichier
    de reference. Sans elle il change d'une execution a l'autre — le probleme est
    trop dur pour converger dans le budget depuis la correction de H8 — et les
    mesures de ce rapport cessent d'etre reproductibles (cf. D12).

    Returns:
        {nom: (Schedule, ProblemInstance)}
    """
    import json

    base = charge_instance_exemple()
    with open(os.path.join(FIXTURES_DIR, "expected_output.json")) as f:
        repro = json.load(f)["reproducibility"]
    optimal = CPSATSolver(
        timeout_seconds=timeout_seconds,
        num_search_workers=repro["num_search_workers"],
        random_seed=repro["random_seed"],
        max_deterministic_time=repro["max_deterministic_time"],
    ).solve(base)
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
