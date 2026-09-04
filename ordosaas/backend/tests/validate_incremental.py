"""
Script de validation du reordonnancement incremental.

Livrable 3 de la Discussion 2, construit sur le modele de `tests/validate_example.py`
(le script de validation deja present dans le depot). Usage :

    python -m tests.validate_incremental            # tous les scenarios
    python -m tests.validate_incremental --jonction # livrable 1 seulement
    python -m tests.validate_incremental --densite  # livrable 2 seulement

Il s'utilise aussi comme bibliotheque, independamment de pytest :

    rapport = valide_resolution(schedule_initial, event, resolution, instance)
    rapport.affiche()
    if not rapport.ok: ...

Chaque verification rend son propre PASS / FAIL / INFO — le script ne s'arrete pas a
la premiere erreur et ne renvoie pas un simple booleen global, afin qu'un diagnostic
complet soit disponible en une seule execution.

## Portee volontairement plus large que le validateur canonique

`scheduling/validation.py` verifie chevauchement, precedence et Cumulative WR. Il ne
verifie **pas** la coherence d'un `SetupEntry` avec le predecesseur reel de son
operation, ni que la place d'un setup manquant existe. C'est precisement ce trou qui
a laisse passer le defaut corrige en D10.

Ce script comble ce trou **pour l'incremental uniquement**, et c'est un choix
delibere : ajouter cette exigence au validateur canonique l'imposerait
retroactivement au solveur LNS initial, jamais concu ni teste sous cet angle, ce qui
sort du perimetre de la Discussion 2. Si un defaut de coherence des setups existe
aussi cote solveur initial, ce sera une decouverte a traiter dans une session dediee.
"""
import logging
import sys
from dataclasses import dataclass, field

from scheduling.incremental import IncrementalConfig, resolve_incremental
from scheduling.models.perturbation import PerturbationType
from scheduling.validation import find_machine_overlaps, validate_schedule

PASS, FAIL, INFO = "PASS", "FAIL", "INFO"


# --------------------------------------------------------------------------
# Structures de rapport
# --------------------------------------------------------------------------
@dataclass
class Verification:
    """Une verification et son verdict, avec le detail de ce qui l'a motive."""

    nom: str
    statut: str
    details: list = field(default_factory=list)

    @property
    def echoue(self) -> bool:
        return self.statut == FAIL


@dataclass
class RapportValidation:
    """L'ensemble des verifications d'une resolution incrementale."""

    scenario: str
    verifications: list = field(default_factory=list)

    def ajoute(self, nom, statut, details=None) -> None:
        self.verifications.append(Verification(nom, statut, list(details or [])))

    @property
    def ok(self) -> bool:
        return not any(v.echoue for v in self.verifications)

    @property
    def nb_echecs(self) -> int:
        return sum(1 for v in self.verifications if v.echoue)

    def affiche(self, indent: str = "") -> None:
        print(f"{indent}=== {self.scenario} ===")
        for v in self.verifications:
            print(f"{indent}[{v.statut}] {v.nom}")
            for detail in v.details:
                print(f"{indent}       {detail}")
        verdict = "OK" if self.ok else f"{self.nb_echecs} ECHEC(S)"
        print(f"{indent}--> {verdict}")


# --------------------------------------------------------------------------
# Verifications
# --------------------------------------------------------------------------
def _occupation_debut(entry) -> int:
    if entry.setup and entry.setup.duration > 0:
        return min(entry.start_time, entry.setup.start_time)
    return entry.start_time


def _par_machine(schedule) -> dict:
    par_machine = {}
    for entry in schedule.entries:
        par_machine.setdefault(entry.machine_id, []).append(entry)
    for entrees in par_machine.values():
        entrees.sort(key=lambda e: e.start_time)
    return par_machine


def verifie_operations_figees(rapport, resolution, t_now) -> None:
    """Aucune operation figee (start_time <= T_now) deplacee ni modifiee.

    C'est l'invariant central de tout l'incremental : une operation commencee est un
    fait accompli, pas une variable.
    """
    fusionnees = {
        (e.job_id, e.position_in_job): e for e in resolution.schedule.entries
    }
    problemes = []
    for figee in resolution.zone.state.frozen_entries:
        cle = (figee.job_id, figee.position_in_job)
        apres = fusionnees.get(cle)
        if apres is None:
            problemes.append(f"operation figee {cle} absente du planning fusionne")
            continue
        if (apres.start_time, apres.end_time, apres.duration) != (
            figee.start_time, figee.end_time, figee.duration
        ):
            problemes.append(
                f"operation figee {cle} modifiee : "
                f"[{figee.start_time}-{figee.end_time}] d={figee.duration} -> "
                f"[{apres.start_time}-{apres.end_time}] d={apres.duration}"
            )
    nb = len(resolution.zone.state.frozen_entries)
    rapport.ajoute(
        f"Operations figees intactes ({nb} a T_now={t_now})",
        FAIL if problemes else PASS,
        problemes,
    )


def verifie_frontieres(rapport, resolution, instance) -> None:
    """Aucun chevauchement aux deux frontieres du planning fusionne."""
    violations = (
        [f"frontiere gauche : {v}" for v in resolution.report.left_boundary_violations]
        + [f"frontiere droite : {v}" for v in resolution.report.right_boundary_violations]
    )
    rapport.ajoute(
        "Frontieres sans chevauchement",
        FAIL if violations else PASS,
        violations,
    )

    globales = validate_schedule(resolution.schedule, instance=instance)
    rapport.ajoute(
        "Planning fusionne valide (precedence, NoOverlap, Cumulative WR)",
        FAIL if globales else PASS,
        globales,
    )


def verifie_setups(rapport, resolution, instance) -> None:
    """Coherence des setups de jonction, et place disponible pour ceux qui manquent.

    Trois familles de verification :

    1. les `SetupEntry` de jonction emis par le modele (cf. D8) doivent avoir une
       duree correcte, des bornes coherentes et ne pas empieter sur l'operation
       qu'ils precedent ;
    2. chaque transition IMPLIQUANT LA ZONE doit disposer d'au moins la place du
       setup qu'elle exige — c'est le controle qui aurait attrape le defaut corrige
       en D10, et qu'aucun validateur ne faisait. Les transitions entre deux
       operations non touchees sont heritees du planning initial et signalees en
       INFO, pas en FAIL (cf. H8) ;
    3. les metadonnees perimees connues (Constat A) sont signalees en INFO et non en
       FAIL, puisque la limite est documentee et sans effet sur la validite.
    """
    problemes, perimes = [], []

    # -- 1. les setups de jonction emis --------------------------------------
    for (job_id, position), setup in resolution.junction_setups.items():
        cible = next(
            (e for e in resolution.schedule.entries
             if e.job_id == job_id and e.position_in_job == position),
            None,
        )
        etiquette = f"setup de jonction {setup.from_job_id}->{job_id}"
        if cible is None:
            problemes.append(f"{etiquette} : operation cible absente du fusionne")
            continue
        attendu = instance.get_setup(setup.from_job_id, job_id, cible.machine_id)
        if setup.duration != attendu:
            problemes.append(
                f"{etiquette} : duree {setup.duration} au lieu de {attendu}"
            )
        if setup.end_time - setup.start_time != setup.duration:
            problemes.append(
                f"{etiquette} : bornes [{setup.start_time}-{setup.end_time}] "
                f"incoherentes avec la duree {setup.duration}"
            )
        if setup.start_time < 0 or setup.duration < 0:
            problemes.append(f"{etiquette} : temps negatif")
        if setup.end_time > cible.start_time:
            problemes.append(
                f"{etiquette} : empiete sur l'operation qui suit "
                f"(setup finit a {setup.end_time}, operation demarre a "
                f"{cible.start_time})"
            )
        if cible.setup is None or cible.setup.start_time != setup.start_time:
            problemes.append(f"{etiquette} : non rattache a l'entree cible apres fusion")

    nb = len(resolution.junction_setups)
    rapport.ajoute(
        f"Setups de jonction coherents ({nb} emis)",
        FAIL if problemes else PASS,
        problemes,
    )

    # -- 2. place disponible pour les transitions dont l'incremental repond ---
    # Une transition n'engage l'incremental que si au moins une des deux operations
    # appartient a la zone reoptimisee. Les transitions entre deux operations que
    # l'incremental n'a pas touchees sont HERITEES du planning initial : les compter
    # en echec reviendrait a reprocher a l'incremental un defaut du solveur initial
    # (cf. H8 — CPSATSolver ne force jamais le booleen de ses setups optionnels, si
    # bien que ses plannings ne reservent aucune place aux setups). Elles sont donc
    # signalees en INFO, avec le renvoi qui convient.
    # Granularite : l'ENTREE reoptimisee, pas le job. Un job peut avoir des
    # operations figees et d'autres dans la zone ; juger par job attribuerait a
    # l'incremental des transitions entre deux operations figees qu'il n'a jamais
    # touchees.
    reoptimisees = {
        (e.job_id, e.position_in_job)
        for e in resolution.window_result.schedule.entries
    }
    manques, herites = [], []
    for machine_id, entrees in _par_machine(resolution.schedule).items():
        for precedente, suivante in zip(entrees, entrees[1:]):
            requis = instance.get_setup(precedente.job_id, suivante.job_id, machine_id)
            if requis <= 0:
                continue
            # L'ecart se mesure jusqu'au debut de l'OPERATION, pas jusqu'au debut
            # d'occupation : c'est precisement dans cet intervalle que le setup doit
            # tenir, et l'y inclure reviendrait a l'exclure de sa propre place.
            espace = suivante.start_time - precedente.end_time
            if espace >= requis:
                continue
            message = (
                f"{machine_id} : transition {precedente.job_id}->{suivante.job_id} "
                f"exige {requis} unites, {espace} disponible(s)"
            )
            engage_zone = (
                (precedente.job_id, precedente.position_in_job) in reoptimisees
                or (suivante.job_id, suivante.position_in_job) in reoptimisees
            )
            (manques if engage_zone else herites).append(message)

    rapport.ajoute(
        "Place reservee pour les transitions impliquant la zone",
        FAIL if manques else PASS,
        manques + ([
            "Cause connue : IncrementalOptimizer._add_setups ne force jamais le "
            "booleen de ses setups optionnels, si bien qu'un setup entre deux "
            "operations de la zone n'est jamais paye — voir H9 dans "
            "docs/CONTEXTE_ET_DECISIONS.md."
        ] if manques else []),
    )
    if herites:
        rapport.ajoute(
            f"Transitions heritees du planning initial sans place de setup "
            f"({len(herites)})",
            INFO,
            herites[:5]
            + ([f"... et {len(herites) - 5} autre(s)"] if len(herites) > 5 else [])
            + ["Defaut du solveur initial, hors perimetre de l'incremental : voir H8 "
               "dans docs/CONTEXTE_ET_DECISIONS.md."],
        )

    # -- 3. metadonnees perimees connues (Constat A) -------------------------
    for machine_id, entrees in _par_machine(resolution.schedule).items():
        for precedente, suivante in zip(entrees, entrees[1:]):
            if suivante.setup is None or suivante.setup.duration <= 0:
                continue
            if suivante.setup.from_job_id == precedente.job_id:
                continue
            perimes.append(
                f"{machine_id} : {suivante.job_id} porte un setup depuis "
                f"{suivante.setup.from_job_id} alors que {precedente.job_id} la "
                f"precede (duree {suivante.setup.duration}, reelle "
                f"{instance.get_setup(precedente.job_id, suivante.job_id, machine_id)})"
            )
    if perimes:
        rapport.ajoute(
            "Metadonnees de setup perimees (limite connue, Constat A / D8)",
            INFO,
            perimes + [
                "Sans effet sur la validite : seule la position temporelle de ces "
                "SetupEntry est fiable, pas from_job_id ni duration."
            ],
        )


def verifie_perimetre(rapport, resolution, schedule_initial) -> None:
    """Le nombre de jobs modifies est coherent avec la taille de l'ImpactZone.

    Detecte une derive silencieuse : un job replanifie alors qu'il n'appartient pas
    a la zone d'impact ne devrait jamais arriver, la zone etant justement l'ensemble
    de ce que le modele a le droit de bouger.
    """
    avant = {
        (e.job_id, e.position_in_job): (e.start_time, e.end_time)
        for e in schedule_initial.entries
    }
    apres = {
        (e.job_id, e.position_in_job): (e.start_time, e.end_time)
        for e in resolution.schedule.entries
    }

    bouges = {
        cle[0] for cle in set(avant) | set(apres)
        if avant.get(cle) != apres.get(cle)
    }
    autorises = set(resolution.zone.impacted_job_ids)
    event = resolution.zone.event
    if event.event_type is PerturbationType.JOB_CANCEL:
        autorises.add(event.payload.job_id)
    elif event.event_type is PerturbationType.URGENT_JOB:
        autorises.add(event.payload.job_id)

    hors_zone = sorted(bouges - autorises)
    details = []
    if hors_zone:
        details.append(
            f"job(s) modifie(s) hors de la zone d'impact : {', '.join(hors_zone)}"
        )
    rapport.ajoute(
        f"Aucune derive hors zone ({len(bouges)} job(s) modifie(s), "
        f"zone de {resolution.zone.nb_impacted_jobs})",
        FAIL if hors_zone else PASS,
        details,
    )

    # Le KPI communique ne doit pas non plus depasser la zone.
    incoherent = resolution.nb_jobs_affected > len(autorises)
    rapport.ajoute(
        f"KPI coherent : {resolution.nb_jobs_affected} job(s) replanifie(s) sur "
        f"{resolution.nb_future_jobs} futurs",
        FAIL if incoherent else PASS,
        [f"KPI {resolution.nb_jobs_affected} > {len(autorises)} jobs autorises"]
        if incoherent else [],
    )


def verifie_contrat_repli(rapport, resolution) -> None:
    """Contrat H5 : le garde-fou SIGNALE le depassement, il ne ROUTE jamais.

    Attention a la lecture du contrat. « Signale mais jamais route » (H5, precise
    par D9) veut dire qu'aucun basculement automatique vers `LNSRecursiveSolver`
    n'a lieu — **pas** qu'aucune modification du planning n'est appliquee. Par
    conception, `resolve_incremental` poursuit et applique la re-optimisation meme
    au-dela du seuil, en laissant l'appelant maitre de la decision ; c'est
    `raise_on_fallback=True` qui donne un echec franc sans planning.

    La verification porte donc sur ce qui est reellement contractuel : le drapeau
    est expose, et la methode reste l'incremental.
    """
    if not resolution.fallback_recommended:
        rapport.ajoute("Garde-fou de repli non declenche", PASS)
        return

    problemes = []
    methode = resolution.schedule.method_used
    if methode != "incremental":
        problemes.append(
            f"routage detecte : method_used = {methode!r} au lieu de 'incremental' "
            f"(H5 : le garde-fou ne doit rien router)"
        )
    if resolution.zone.fallback_recommended is not True:
        problemes.append("le drapeau de repli n'est pas expose sur la zone")

    rapport.ajoute(
        f"Repli recommande ({round(100 * resolution.zone.ratio_future_jobs_affected)} "
        f"% des jobs futurs) et non route",
        FAIL if problemes else PASS,
        problemes,
    )
    rapport.ajoute(
        "Planning incremental tout de meme applique",
        INFO,
        ["Comportement documente (H5 / D9) : la cascade signale et poursuit. "
         "Utiliser raise_on_fallback=True pour un echec franc sans planning."],
    )


def valide_resolution(schedule_initial, event, resolution, instance,
                      t_now=None, scenario: str = "resolution incrementale"):
    """Valide une resolution incrementale et renvoie un rapport detaille.

    Args:
        schedule_initial: le Schedule d'avant la perturbation.
        event: le PerturbationEvent declencheur.
        resolution: l'IncrementalResolution rendue par `resolve_incremental`.
        instance: la ProblemInstance de reference.
        t_now: instant present ; par defaut celui porte par la zone.
        scenario: libelle affiche en tete de rapport.

    Returns:
        RapportValidation — `.ok` est faux des qu'une verification echoue.
    """
    t_now = resolution.zone.t_now if t_now is None else t_now
    rapport = RapportValidation(scenario=scenario)

    verifie_operations_figees(rapport, resolution, t_now)
    verifie_frontieres(rapport, resolution, instance)
    verifie_setups(rapport, resolution, instance)
    verifie_perimetre(rapport, resolution, schedule_initial)
    verifie_contrat_repli(rapport, resolution)
    return rapport


# --------------------------------------------------------------------------
# Execution autonome sur les scenarios des livrables 1 et 2
# --------------------------------------------------------------------------
def _rapports_jonction() -> list:
    """Les scenarios du livrable 1, rejoues tels quels."""
    from tests.scenarios_jonction import SCENARIOS

    rapports = []
    for nom, constructeur in SCENARIOS.items():
        schedule, instance, event = constructeur()
        resolution = resolve_incremental(
            schedule, event, instance,
            config=IncrementalConfig(search_horizon=10_000, max_impacted_jobs=50,
                                     timeout_seconds=10, stability_weight=0.0),
        )
        rapports.append(valide_resolution(
            schedule, event, resolution, instance,
            scenario=f"livrable 1 — {nom}",
        ))
    return rapports


def _rapports_densite() -> list:
    """Les scenarios du livrable 2, rejoues tels quels, dans les deux regimes."""
    from tests.densite_report import REGIMES, _perturbations
    from tests.densite_variants import DENSITES, construit_variantes

    variantes = construit_variantes()
    rapports = []
    for nom in DENSITES:
        schedule, instance = variantes[nom]
        t_now = schedule.horizon // 3
        for libelle, event in _perturbations(schedule, instance, t_now):
            for regime, config in REGIMES.items():
                resolution = resolve_incremental(
                    schedule, event, instance, t_now=t_now, config=config
                )
                rapports.append(valide_resolution(
                    schedule, event, resolution, instance, t_now=t_now,
                    scenario=f"livrable 2 — {nom} / {libelle} / {regime}",
                ))
    return rapports


def main() -> int:
    logging.disable(logging.WARNING)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    jonction = "--densite" not in sys.argv
    densite = "--jonction" not in sys.argv

    print("=" * 74)
    print("VALIDATION DU REORDONNANCEMENT INCREMENTAL")
    print("=" * 74)
    print()

    rapports = []
    if jonction:
        rapports += _rapports_jonction()
    if densite:
        print("Resolution des variantes de densite (CP-SAT)...")
        print()
        rapports += _rapports_densite()

    for rapport in rapports:
        rapport.affiche()
        print()

    echecs = [r for r in rapports if not r.ok]
    total_verifs = sum(len(r.verifications) for r in rapports)
    infos = sum(
        1 for r in rapports for v in r.verifications if v.statut == INFO
    )

    print("=" * 74)
    print(f"{len(rapports)} scenario(s), {total_verifs} verification(s), "
          f"{infos} information(s)")
    if echecs:
        print(f"[FAIL] {len(echecs)} scenario(s) en echec :")
        for r in echecs:
            for v in r.verifications:
                if v.echoue:
                    print(f"   - {r.scenario} : {v.nom}")
        return 1
    print("[PASS] TOUS LES SCENARIOS VALIDES")
    return 0


if __name__ == "__main__":
    sys.exit(main())
