"""
Orchestrateur public du reordonnancement incremental.

Point d'entree unique de la cascade decrite en Sec. 2.4 de
docs/architecture-incremental.md. Il enchaine les six composants dans l'ordre :

    PerturbationEvent
        -> ScheduleStateManager      (fige / futur, selon T_now)
        -> ImpactAnalyzer            (zone a re-optimiser + garde-fou de repli)
        -> IncrementalContextBuilder (les deux contextes exacts)
        -> IncrementalOptimizer      (CP-SAT sur la zone, avec stabilite)
        -> ScheduleMerger            (recollement + validation des frontieres)

`ScheduleStateManager` n'apparait pas explicitement ci-dessous : `ImpactAnalyzer`
l'invoque lui-meme et publie son resultat sur `ImpactZone.state`, qui est ensuite
consomme par le builder de contextes et par le merger. Le faire tourner une seconde
fois ici donnerait deux decoupages distincts du meme planning.

C'est ce module qu'appellera le worker de la Discussion 3 : les tests de scenarios
passent deliberement par lui, pour qu'aucun chemin de code ne soit teste
differemment de ce qui tournera en production.

Deux ecarts assumes par rapport a la signature esquissee dans le prompt
(`resolve_incremental(schedule, event, t_now, config) -> Schedule`) :

1. `instance` est un parametre obligatoire. Tous les composants en dependent — le
   builder de sous-instance, les durees de setup, la Cumulative WR, le recalcul des
   KPI — et rien ne permet de la retrouver depuis un `Schedule` seul.
2. Le retour est un `IncrementalResolution`, pas un `Schedule` nu. Le planning
   fusionne y est accessible par `.schedule`, mais un `Schedule` seul perdrait le
   `MergeReport`, dont le worker a besoin pour le KPI de communication
   ("6 jobs replanifies sur 180", Sec. 2.4) et l'endpoint de diff de la Discussion 4.
"""
import logging
from dataclasses import dataclass, field

from scheduling.components.impact_analyzer import ImpactAnalyzer
from scheduling.components.incremental_context_builder import IncrementalContextBuilder
from scheduling.components.schedule_merger import ScheduleMerger
from scheduling.solvers.incremental_optimizer import (
    DEFAULT_STABILITY_WEIGHT,
    DEFAULT_TIMEOUT_SECONDS,
    IncrementalOptimizer,
)

logger = logging.getLogger(__name__)


class IncrementalResolutionError(Exception):
    """La cascade n'a pas pu produire de planning."""


@dataclass
class IncrementalConfig:
    """Reglages de la cascade, regroupes en un seul objet.

    Les valeurs par defaut sont celles des composants : cet objet ne redefinit
    aucune politique, il ne fait que rassembler les points de reglage pour que
    l'appelant (worker, API, tests) n'ait pas a instancier six objets a la main.

    Les bornes de la zone sont des FRACTIONS de l'instance traitee (cf. D7 :
    l'unite de temps du projet est abstraite). `search_horizon` et
    `max_impacted_jobs` restent disponibles comme surcharges absolues.
    """

    # -- ImpactAnalyzer -----------------------------------------------------
    search_horizon_fraction: float = None
    max_impacted_jobs_fraction: float = None
    fallback_threshold: float = None
    min_search_horizon: int = None
    min_impacted_jobs: int = None
    search_horizon: int = None  # surcharge absolue
    max_impacted_jobs: int = None  # surcharge absolue

    # -- IncrementalOptimizer -----------------------------------------------
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    stability_weight: float = DEFAULT_STABILITY_WEIGHT
    num_search_workers: int = 4

    # -- ScheduleMerger -----------------------------------------------------
    strict_merge: bool = True

    # -- Garde-fou de repli (Sec. 2.6) --------------------------------------
    # False par defaut : la cascade SIGNALE le depassement de seuil sur
    # `IncrementalResolution.fallback_recommended` mais poursuit. Le routage reel
    # vers LNSRecursiveSolver reste hors perimetre (hypothese H5). Mettre a True
    # donne un echec franc plutot qu'un simple drapeau.
    raise_on_fallback: bool = False

    def build_analyzer(self) -> ImpactAnalyzer:
        """ImpactAnalyzer configure, sans reecrire les defauts du composant."""
        kwargs = {
            "search_horizon_fraction": self.search_horizon_fraction,
            "max_impacted_jobs_fraction": self.max_impacted_jobs_fraction,
            "fallback_threshold": self.fallback_threshold,
            "min_search_horizon": self.min_search_horizon,
            "min_impacted_jobs": self.min_impacted_jobs,
            "search_horizon": self.search_horizon,
            "max_impacted_jobs": self.max_impacted_jobs,
        }
        # Un None signifie "garder le defaut du composant", pas "passer None" :
        # min_search_horizon et les surcharges absolues acceptent None, mais les
        # fractions et les seuils, non.
        return ImpactAnalyzer(**{k: v for k, v in kwargs.items() if v is not None})

    def build_optimizer(self) -> IncrementalOptimizer:
        return IncrementalOptimizer(
            timeout_seconds=self.timeout_seconds,
            stability_weight=self.stability_weight,
            num_search_workers=self.num_search_workers,
        )


@dataclass
class IncrementalResolution:
    """Ce que la cascade a produit, et de quoi le justifier.

    `schedule` est le planning complet fusionne — figé + zone reoptimisee + futur
    non touche. Les autres champs sont l'etat intermediaire, conserve parce que les
    appelants en ont reellement besoin : le worker pour le KPI et la progression,
    l'endpoint de diff pour savoir quoi comparer, les tests pour verifier les
    invariants sur autre chose que le resultat final.
    """

    schedule: object  # Schedule fusionne
    zone: object  # ImpactZone
    window_result: object  # WindowResult d'IncrementalOptimizer
    report: object  # MergeReport
    junction_setups: dict = field(default_factory=dict)

    @property
    def nb_jobs_affected(self) -> int:
        """KPI de communication : "6 jobs replanifies sur 180" (Sec. 2.4)."""
        return self.report.nb_jobs_affected

    @property
    def nb_future_jobs(self) -> int:
        return self.zone.nb_future_jobs

    @property
    def fallback_recommended(self) -> bool:
        """La zone depasse le seuil : une resolution complete serait preferable.

        Signale, jamais route — cf. H5. L'appelant reste maitre de la decision.
        """
        return self.zone.fallback_recommended

    @property
    def is_clean(self) -> bool:
        """Aucune violation aux deux frontieres du recollement."""
        return self.report.is_clean


def resolve_incremental(schedule, event, instance, t_now: int = None,
                        config: IncrementalConfig = None) -> IncrementalResolution:
    """Rejoue la cascade incrementale complete sur un planning existant.

    Args:
        schedule: le Schedule issu de la resolution precedente, deja optimise.
        event: le PerturbationEvent declencheur.
        instance: la ProblemInstance correspondante.
        t_now: instant present ; par defaut `event.timestamp`.
        config: reglages de la cascade ; par defaut ceux des composants.

    Returns:
        IncrementalResolution — `.schedule` porte le planning fusionne.

    Raises:
        IncrementalResolutionError: si CP-SAT ne trouve aucune solution sur la zone.
        IncrementalNotSuitableError: si `config.raise_on_fallback` est vrai et que
            la zone depasse le seuil de repli.
        ScheduleMergeError: si `config.strict_merge` est vrai et que le recollement
            produirait un planning invalide.
    """
    config = config or IncrementalConfig()
    t_now = event.timestamp if t_now is None else t_now

    analyzer = config.build_analyzer()
    zone = analyzer.analyze(event, schedule, instance, t_now=t_now)
    if config.raise_on_fallback:
        analyzer.check_suitability(zone)

    contexts = IncrementalContextBuilder().build(zone, instance)
    window_result = config.build_optimizer().optimize(zone, contexts, instance)
    if window_result is None:
        raise IncrementalResolutionError(
            f"Aucune solution trouvee sur la zone d'impact "
            f"({zone.nb_impacted_jobs} job(s), {len(zone.impacted_entries)} operation(s)) "
            f"en {config.timeout_seconds}s."
        )

    merged, report = ScheduleMerger().merge(
        zone, window_result, instance, strict=config.strict_merge
    )
    logger.info(
        "resolve_incremental: %s a T_now=%d -> %d job(s) replanifie(s) sur %d futurs"
        "%s",
        event.event_type.value, t_now, report.nb_jobs_affected, zone.nb_future_jobs,
        " [repli recommande]" if zone.fallback_recommended else "",
    )
    return IncrementalResolution(
        schedule=merged,
        zone=zone,
        window_result=window_result,
        report=report,
        junction_setups=window_result.junction_setups,
    )
