"""
ScheduleMerger : recolle les trois segments en un Schedule coherent.

Les trois segments (cf. docs/architecture-incremental.md Sec. 2.4, etape 6) :

    [ 1. FIGE ]------[ 2. ZONE REOPTIMISEE ]------[ 3. FUTUR NON TOUCHE ]
              ^                                  ^
        frontiere gauche                  frontiere droite

Les deux frontieres sont verifiees explicitement : c'est la la seule vraie
difficulte du recollement, chaque segment etant valide isolement par construction.
La verification s'appuie sur `scheduling.validation`, endroit de verite unique du
projet (decision D3). Note : `InterWindowOptimizer` ne contient aucune validation de
chevauchement a reutiliser — il ne calcule que des COUTS de jonction — donc rien
n'est duplique ici.
"""
import logging
from dataclasses import dataclass, field

from scheduling.models.perturbation import PerturbationType
from scheduling.models.schedule import Schedule
from scheduling.validation import (
    ScheduleValidationError,
    find_machine_overlaps,
    validate_schedule,
)

logger = logging.getLogger(__name__)


class ScheduleMergeError(ScheduleValidationError):
    """La fusion produirait un planning invalide (typiquement un chevauchement)."""


@dataclass
class MergeReport:
    """Ce que la fusion a produit, pour le KPI de communication et le diff."""

    nb_frozen_entries: int = 0
    nb_reoptimized_entries: int = 0
    nb_untouched_entries: int = 0
    # Jobs dont au moins une operation a change de date par rapport a l'original.
    moved_job_ids: set = field(default_factory=set)
    left_boundary_violations: list = field(default_factory=list)
    right_boundary_violations: list = field(default_factory=list)

    @property
    def nb_jobs_affected(self) -> int:
        """KPI de communication : "6 jobs replanifies sur 180" (Sec. 2.4)."""
        return len(self.moved_job_ids)

    @property
    def is_clean(self) -> bool:
        return not (self.left_boundary_violations or self.right_boundary_violations)


class ScheduleMerger:
    """Fusionne fige + zone reoptimisee + futur non touche."""

    def merge(self, zone, window_result, instance, strict: bool = True):
        """Recolle les trois segments et valide le resultat.

        Args:
            zone: l'ImpactZone (porte le fige et le futur non touche).
            window_result: le WindowResult d'IncrementalOptimizer (la zone).
            instance: la ProblemInstance de reference.
            strict: si True, leve ScheduleMergeError des qu'une frontiere est
                invalide. Si False, renvoie quand meme et le rapport porte les
                violations.

        Returns:
            (Schedule fusionne, MergeReport)
        """
        frozen = list(zone.state.frozen_entries)
        reoptimized = list(window_result.schedule.entries) if window_result else []
        untouched = list(zone.untouched_future_entries)

        merged = Schedule(
            entries=frozen + reoptimized + untouched,
            method_used="incremental",
            solver_status=(
                window_result.schedule.solver_status if window_result else None
            ),
        )
        merged.entries.sort(key=lambda e: (e.machine_id, e.start_time))

        report = MergeReport(
            nb_frozen_entries=len(frozen),
            nb_reoptimized_entries=len(reoptimized),
            nb_untouched_entries=len(untouched),
            moved_job_ids=self._moved_jobs(zone, reoptimized),
            left_boundary_violations=self._check_boundary(frozen, reoptimized, "gauche"),
            right_boundary_violations=self._check_boundary(reoptimized, untouched, "droite"),
        )

        jobs = self._effective_jobs(zone, instance)
        merged.compute_kpis(jobs)

        violations = report.left_boundary_violations + report.right_boundary_violations
        violations += validate_schedule(merged, instance=instance)
        if violations:
            message = (
                f"Fusion invalide ({len(violations)} violation(s)) :\n  - "
                + "\n  - ".join(violations)
            )
            if strict:
                raise ScheduleMergeError(message)
            logger.warning(message)

        logger.info(
            "Fusion : %d figee(s) + %d reoptimisee(s) + %d non touchee(s) ; "
            "%d job(s) replanifie(s)",
            report.nb_frozen_entries, report.nb_reoptimized_entries,
            report.nb_untouched_entries, report.nb_jobs_affected,
        )
        return merged, report

    # ----------------------------------------------------------------------
    @staticmethod
    def _check_boundary(segment_gauche, segment_droit, nom: str) -> list:
        """Chevauchements entre deux segments adjacents, machine par machine.

        On ne valide QUE la jonction : chaque segment est deja valide isolement
        (le fige vient d'une resolution passee, la zone du solveur, le futur non
        touche de la resolution precedente). Passer les deux segments ensemble a
        `find_machine_overlaps` et retrancher les violations internes reviendrait
        au meme, en moins lisible.
        """
        if not segment_gauche or not segment_droit:
            return []
        jonction = Schedule(entries=list(segment_gauche) + list(segment_droit))
        violations = find_machine_overlaps(jonction)
        # Un chevauchement interne a un segment n'est pas un probleme de frontiere.
        internes = set(find_machine_overlaps(Schedule(entries=list(segment_gauche))))
        internes |= set(find_machine_overlaps(Schedule(entries=list(segment_droit))))
        return [
            f"Frontiere {nom} : {v}" for v in violations if v not in internes
        ]

    @staticmethod
    def _moved_jobs(zone, reoptimized) -> set:
        """Jobs dont une operation a reellement change de date.

        Un job present dans la zone mais replace exactement au meme endroit n'a pas
        bouge : il ne compte pas dans le KPI communique au planificateur.
        """
        origine = {
            (e.job_id, e.position_in_job): (e.start_time, e.end_time)
            for e in zone.state.future_entries
        }
        bouges = set()
        for entry in reoptimized:
            avant = origine.get((entry.job_id, entry.position_in_job))
            if avant is None or avant != (entry.start_time, entry.end_time):
                bouges.add(entry.job_id)
        # Un job annule disparait du planning : c'est aussi un changement.
        if zone.event.event_type is PerturbationType.JOB_CANCEL:
            bouges.add(zone.event.payload.job_id)
        return bouges

    @staticmethod
    def _effective_jobs(zone, instance) -> list:
        """Liste de jobs a jour pour le recalcul des KPI.

        Le job annule en sort, le job urgent y entre : sinon `compute_kpis` compte
        un retard sur un job qui n'existe plus, ou en oublie un nouveau.
        """
        from scheduling.models.job import Job

        event = zone.event
        jobs = list(instance.jobs)
        if event.event_type is PerturbationType.JOB_CANCEL:
            jobs = [j for j in jobs if j.id != event.payload.job_id]
        elif event.event_type is PerturbationType.URGENT_JOB:
            payload = event.payload
            if not any(j.id == payload.job_id for j in jobs):
                jobs.append(Job(
                    id=payload.job_id,
                    operations=sorted(payload.operations, key=lambda o: o.position),
                    deadline=payload.deadline, weight=payload.weight,
                ))
        return jobs
