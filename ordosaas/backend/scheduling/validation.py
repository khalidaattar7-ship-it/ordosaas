"""
Validation canonique d'un Schedule : precedence, NoOverlap, Cumulative WR.

Endroit de verite unique du projet pour "ce planning est-il valide ?" (decision D3
de docs/CONTEXTE_ET_DECISIONS.md). Cette logique existait auparavant dupliquee dans
deux fichiers de test — `tests/conftest.py::assert_no_machine_overlap` et
`tests/validate_example.py::validate_no_overlap` — qui delegent desormais ici.

Le module vit au niveau de `scheduling/` et non dans `models/` : les dataclasses du
projet sont des contrats de donnees purs, la validation appartient aux composants.

Les fonctions renvoient des listes de violations lisibles plutot que de lever :
l'appelant decide s'il veut une exception (`assert_valid_schedule`) ou un rapport.
"""
from collections import defaultdict


class ScheduleValidationError(AssertionError):
    """Le Schedule viole au moins une contrainte du probleme."""


# --------------------------------------------------------------------------
# NoOverlap : une machine ne fait qu'une chose a la fois (operations ET setups)
# --------------------------------------------------------------------------
def find_machine_overlaps(schedule) -> list:
    """Chevauchements sur une meme machine, setups compris."""
    slots = defaultdict(list)
    for entry in schedule.entries:
        slots[entry.machine_id].append(
            (entry.start_time, entry.end_time, f"{entry.job_id}#{entry.position_in_job}")
        )
        if entry.setup and entry.setup.duration > 0:
            slots[entry.machine_id].append((
                entry.setup.start_time, entry.setup.end_time,
                f"setup {entry.setup.from_job_id}->{entry.job_id}",
            ))

    violations = []
    for machine_id, intervalles in slots.items():
        intervalles.sort()
        for k in range(len(intervalles) - 1):
            fin, debut_suivant = intervalles[k][1], intervalles[k + 1][0]
            if fin > debut_suivant:
                violations.append(
                    f"Chevauchement sur {machine_id} : {intervalles[k][2]} "
                    f"[{intervalles[k][0]}-{fin}] et {intervalles[k + 1][2]} "
                    f"[{debut_suivant}-{intervalles[k + 1][1]}]"
                )
    return violations


# --------------------------------------------------------------------------
# Precedence : les operations d'un job s'enchainent dans l'ordre des positions
# --------------------------------------------------------------------------
def find_precedence_violations(schedule) -> list:
    par_job = defaultdict(list)
    for entry in schedule.entries:
        par_job[entry.job_id].append(entry)

    violations = []
    for job_id, entrees in par_job.items():
        ordonnees = sorted(entrees, key=lambda e: e.position_in_job)
        for k in range(len(ordonnees) - 1):
            if ordonnees[k].end_time > ordonnees[k + 1].start_time:
                violations.append(
                    f"Precedence violee pour {job_id} : position "
                    f"{ordonnees[k].position_in_job} finit a {ordonnees[k].end_time}, "
                    f"position {ordonnees[k + 1].position_in_job} demarre a "
                    f"{ordonnees[k + 1].start_time}"
                )
    return violations


# --------------------------------------------------------------------------
# Cumulative WR : au plus `wr` setups simultanes, toutes machines confondues
# --------------------------------------------------------------------------
def find_wr_violations(schedule, wr: int) -> list:
    """Verifie qu'au plus `wr` setups tournent en parallele a tout instant.

    Balayage evenementiel : on ne teste la charge qu'aux instants ou elle change,
    ce qui suffit puisqu'elle est constante entre deux bornes.
    """
    if wr <= 0:
        return []

    evenements = []
    for entry in schedule.entries:
        if entry.setup and entry.setup.duration > 0:
            evenements.append((entry.setup.start_time, 1))
            evenements.append((entry.setup.end_time, -1))
    if not evenements:
        return []

    # Les fins passent avant les debuts a instant egal : deux setups qui se
    # touchent bout a bout ne sont pas simultanes.
    evenements.sort(key=lambda x: (x[0], x[1]))

    violations, charge = [], 0
    for instant, delta in evenements:
        charge += delta
        if charge > wr:
            violations.append(
                f"Cumulative WR violee a t={instant} : {charge} setups simultanes "
                f"pour WR={wr}"
            )
            break  # une seule violation suffit a invalider, inutile de saturer
    return violations


# --------------------------------------------------------------------------
# Validation complete
# --------------------------------------------------------------------------
def validate_schedule(schedule, instance=None, wr: int = None) -> list:
    """Toutes les violations d'un Schedule, dans une seule liste.

    Args:
        schedule: le Schedule a valider.
        instance: la ProblemInstance ; si fournie, `wr` en est deduit.
        wr: nombre de techniciens, s'il n'y a pas d'instance sous la main.

    Returns:
        Liste de messages de violation. Vide si le planning est valide.
    """
    if wr is None and instance is not None:
        wr = instance.wr
    violations = find_machine_overlaps(schedule) + find_precedence_violations(schedule)
    if wr is not None:
        violations += find_wr_violations(schedule, wr)
    return violations


def assert_valid_schedule(schedule, instance=None, wr: int = None) -> None:
    """Leve ScheduleValidationError si le planning viole une contrainte."""
    violations = validate_schedule(schedule, instance=instance, wr=wr)
    if violations:
        raise ScheduleValidationError(
            f"{len(violations)} violation(s) :\n  - " + "\n  - ".join(violations)
        )
