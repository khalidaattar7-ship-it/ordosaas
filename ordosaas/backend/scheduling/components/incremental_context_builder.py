"""
IncrementalContextBuilder : les deux contextes de frontiere de la zone d'impact.

DIFFERENCE STRUCTURELLE AVEC LE LNS INITIAL (cf. docs/architecture-incremental.md
Sec. 2.1). Dans le LNS initial, `ContextPropagator` pose comme regle que le contexte
gauche est exact (fenetre precedente deja optimisee) et le contexte droit
APPROXIMATIF (planning ATCS, pas encore optimise). Dans le reordonnancement
incremental, les DEUX contextes sont EXACTS :

- contexte GAUCHE  : l'etat reel a T_now. Ce n'est meme plus une optimisation, c'est
                     un fait accompli — les operations figees ont demarre.
- contexte DROIT   : le planning futur au-dela de la zone d'impact. Il vient de la
                     resolution precedente DEJA OPTIMISEE ; il est simplement non
                     retouche. Il n'y a aucune approximation ATCS ici.

On coordonne donc deux verites (passe fige, futur deja optimise), pas une verite et
une approximation : c'est structurellement plus favorable que le LNS initial.

Le calcul commun est delegue a `ContextPropagator`, non modifiee. Les deux ecarts
assumes (contexte droit alimente par le Schedule reel plutot que par l'ATCS, et
contexte droit porteur de `machine_loads` a lire comme une date au plus tard) sont
justifies en detail dans docs/CONTEXTE_ET_DECISIONS.md, decision D6.
"""
from dataclasses import dataclass

from scheduling.components.context_propagator import ContextPropagator
from scheduling.models.context import BoundaryContext
from scheduling.models.schedule import Schedule
from scheduling.models.window import Window, WindowResult


@dataclass
class IncrementalContexts:
    """Les deux contextes exacts encadrant la zone d'impact."""

    left: BoundaryContext
    right: BoundaryContext
    # Rappel explicite : contrairement au LNS initial, aucun des deux n'est approximatif.
    left_is_exact: bool = True
    right_is_exact: bool = True


class IncrementalContextBuilder:
    """Construit les contextes gauche et droit d'une ImpactZone."""

    def __init__(self, propagator: ContextPropagator = None):
        self.propagator = propagator or ContextPropagator()

    # ----------------------------------------------------------------------
    def build(self, zone, instance) -> IncrementalContexts:
        """Construit les deux contextes exacts pour une ImpactZone donnee."""
        return IncrementalContexts(
            left=self.build_left_context(zone, instance),
            right=self.build_right_context(zone, instance),
        )

    def build_left_context(self, zone, instance) -> BoundaryContext:
        """Contexte gauche EXACT : l'etat fige reel a T_now.

        Delegue a `ContextPropagator.build_left_context()` en lui presentant les
        entrees figees comme le resultat d'une fenetre precedente — le calcul est
        exactement le meme (derniere operation et charge par machine, jobs deja
        engages, jobs a cheval sur la frontiere).

        Ajout par rapport au LNS : `active_setups` est reellement rempli avec les
        setups figes qui chevauchent T_now. Ils consomment un technicien au-dela de
        T_now et doivent donc compter dans la contrainte Cumulative WR de la zone.
        """
        state = zone.state
        frozen_schedule = Schedule(entries=list(state.frozen_entries), method_used="frozen")
        pseudo_result = WindowResult(
            window=Window(index=0, t_start=0, t_end=state.t_now, jobs=list(instance.jobs)),
            schedule=frozen_schedule,
            exit_context=BoundaryContext.empty(),
            objective=0.0,
            method="frozen",
        )
        context = self.propagator.build_left_context(pseudo_result, instance)
        context.active_setups = self._active_setups_at(state)
        return context

    def build_right_context(self, zone, instance) -> BoundaryContext:
        """Contexte droit EXACT : le planning futur non touche, au-dela de la zone.

        Deux differences avec le contexte droit du LNS initial (cf. D6) :

        1. La source est le Schedule REEL deja optimise, pas une approximation ATCS.
           `ContextPropagator.build_right_context()` est reutilisee telle quelle, on
           ne fait que lui passer une meilleure entree.
        2. `machine_loads` est rempli, alors que le LNS le laisse vide. Il porte ici
           le debut de la premiere operation non touchee de chaque machine, a lire
           comme une DATE AU PLUS TARD pour la zone : la partie reoptimisee ne doit
           pas deborder dessus. C'est ce qui rend ce contexte contraignant et non
           purement informationnel.
        """
        untouched = zone.untouched_future_entries
        untouched_schedule = Schedule(entries=list(untouched), method_used="untouched")
        jobs_by_id = {j.id: j for j in instance.jobs}
        jobs_apres = [
            jobs_by_id[job_id]
            for job_id in {e.job_id for e in untouched}
            if job_id in jobs_by_id
        ]
        fenetre_apres = Window(
            index=1,
            t_start=min((e.start_time for e in untouched), default=state_t_end(zone)),
            t_end=max((e.end_time for e in untouched), default=state_t_end(zone)),
            jobs=jobs_apres,
        )
        context = self.propagator.build_right_context(
            fenetre_apres, untouched_schedule, instance
        )
        context.machine_loads = self._earliest_untouched_start_per_machine(untouched)
        context.incomplete_jobs = {}
        return context

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _active_setups_at(state) -> list:
        """Setups figes encore en cours a T_now, au format attendu par le solveur.

        Format : [(machine_id, from_job_id, to_job_id, start_time, end_time)] —
        celui que `CPSATSolver.solve_with_context` sait deja consommer pour la
        contrainte Cumulative.
        """
        actifs = []
        for entry in state.frozen_entries:
            setup = entry.setup
            if setup is None or setup.duration <= 0:
                continue
            if setup.start_time <= state.t_now < setup.end_time:
                actifs.append((
                    entry.machine_id, setup.from_job_id, entry.job_id,
                    setup.start_time, setup.end_time,
                ))
        return actifs

    @staticmethod
    def _earliest_untouched_start_per_machine(untouched) -> dict:
        """{machine_id: debut de la premiere entree future non touchee}.

        Le setup precede l'operation : c'est lui qui marque le debut reel
        d'occupation de la machine, donc la vraie date au plus tard pour la zone.
        """
        bornes: dict = {}
        for entry in untouched:
            debut = entry.start_time
            if entry.setup and entry.setup.duration > 0:
                debut = min(debut, entry.setup.start_time)
            actuel = bornes.get(entry.machine_id)
            if actuel is None or debut < actuel:
                bornes[entry.machine_id] = debut
        return bornes


def state_t_end(zone) -> int:
    """Repli quand il n'y a aucune entree non touchee : la frontiere vaut T_now."""
    return zone.state.t_now
