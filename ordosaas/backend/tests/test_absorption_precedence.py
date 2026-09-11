"""
Absorption sur la cascade de precedence (D14).

Avant D14, la precedence propageait TOUT retard a TOUTES les operations en aval d'un
job, sans jamais verifier si le temps mort deja present entre deux operations
consecutives pouvait l'absorber. Elle ne convergeait donc jamais d'elle-meme et
surestimait systematiquement la propagation.

Elle applique desormais le meme principe que la contention : on descend la chaine du
job en soustrayant le temps mort rencontre, et on s'arrete des que le retard est
epuise. Le trou se mesure sur les bornes d'OPERATION pures
(`suivant.start_time - curseur`), jamais sur l'occupation incluant le setup.

## Comment ces tests observent l'absorption

La zone est de granularite JOB : `analyze()` y retient toutes les operations futures
d'un job marque. Une absorption INTERNE a un job est donc invisible dans
`impacted_job_ids` — un premier jeu de tests ecrit naivement sur ce champ passait
identiquement avec et sans le correctif, et ne prouvait donc rien.

L'effet observable, et le seul qui compte en pratique, est INDIRECT : chaque operation
que la precedence marque declenche une cascade de CONTENTION sur sa machine. En
s'arretant plus tot, la precedence evite d'ouvrir ces cascades et ne touche donc pas
les jobs voisins. Chaque test place donc un job TEMOIN juste derriere l'operation
concernee, et verifie s'il est atteint ou non.
"""
import pytest

from scheduling.components.impact_analyzer import (
    REASON_CONTENTION,
    ImpactAnalyzer,
)
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.perturbation import make_event
from scheduling.models.schedule import Schedule, ScheduleEntry, SetupEntry


def _entry(job_id, machine_id, position, start, duration, setup=None):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine_id, position_in_job=position,
        start_time=start, end_time=start + duration, duration=duration, setup=setup,
    )


def _mono(job_id, machine_id, start, duration=50):
    """Un job temoin d'une seule operation, place derriere une operation de J1."""
    return (
        _entry(job_id, machine_id, 1, start, duration),
        Job(id=job_id, operations=[Operation(job_id, machine_id, duration, 1)],
            deadline=9000, weight=1.0),
    )


def _atelier(ops_j1, temoins):
    """J1 sur M1/M2/M3 aux dates donnees, plus des jobs temoins.

    Args:
        ops_j1: dates de debut des trois operations de J1.
        temoins: liste de (job_id, machine_id, debut).
    """
    entries = [
        _entry("J1", f"M{k + 1}", k + 1, debut, 50)
        for k, debut in enumerate(ops_j1)
    ]
    jobs = [Job(
        id="J1",
        operations=[Operation("J1", f"M{k + 1}", 50, k + 1) for k in range(len(ops_j1))],
        deadline=9000, weight=1.0,
    )]
    for job_id, machine_id, debut in temoins:
        entry, job = _mono(job_id, machine_id, debut)
        entries.append(entry)
        jobs.append(job)
    machines = sorted({e.machine_id for e in entries})
    instance = ProblemInstance(jobs=jobs, machines=machines, setup_times={}, wr=1)
    return Schedule(entries=entries), instance


def _allonge_op1(nouvelle_duree=100):
    """Allonge la premiere operation de J1 : le retard part de la."""
    return make_event("duration_change", timestamp=50, job_id="J1",
                      position_in_job=1, machine_id="M1",
                      new_duration=nouvelle_duree)


def _analyse(schedule, instance, event=None, **bornes):
    base = dict(search_horizon=10_000, max_impacted_jobs=50)
    base.update(bornes)
    return ImpactAnalyzer(**base).analyze(
        event or _allonge_op1(), schedule, instance
    )


# ==========================================================================
# Le retard est absorbe : la propagation s'arrete
# ==========================================================================
def test_le_temps_mort_du_job_absorbe_le_retard():
    """Convergence naturelle : le trou suffit, l'operation suivante ne bouge pas.

    J1 : op1[100-150] puis op2[400-450] sur M2 — un trou de 250 unites. Le temoin W2
    suit immediatement op2 sur M2.

    L'operation 1 passe de 50 a 100 unites, soit 50 de retard. Le trou l'absorbe
    entierement : op2 ne bouge pas, donc W2 n'est jamais atteint. Sans absorption,
    op2 aurait ete marquee et sa contention aurait emporte W2.
    """
    schedule, instance = _atelier([100, 400], [("W2", "M2", 450)])
    zone = _analyse(schedule, instance)

    assert zone.impacted_job_ids == {"J1"}, (
        "le retard s'eteint dans le job : aucun voisin ne doit etre touche"
    )
    assert zone.truncated is False, "rien n'a ete coupe, la cascade a converge"


def test_labsorption_est_cumulative_le_long_de_la_chaine():
    """Deux trous successifs mangent le retard petit a petit.

    J1 : op1[100-150], op2[170-220], op3[400-450].
    Trou op1->op2 = 20, trou op2->op3 = 180. Retard initial 50 : il en reste 30 apres
    le premier trou, donc op2 bouge et son temoin W2 est atteint ; puis 30 - 180 <= 0,
    donc op3 ne bouge pas et son temoin W3 est epargne.

    C'est le caractere CUMULATIF qui est verifie ici : un seul trou ne suffisait pas,
    la somme des deux oui.
    """
    schedule, instance = _atelier(
        [100, 170, 400], [("W2", "M2", 220), ("W3", "M3", 450)]
    )
    zone = _analyse(schedule, instance)

    assert "W2" in zone.impacted_job_ids, "le premier trou ne suffisait pas"
    assert "W3" not in zone.impacted_job_ids, "le second trou a fini d'absorber"


# ==========================================================================
# Le retard depasse le temps mort : la propagation continue
# ==========================================================================
def test_un_retard_superieur_au_temps_mort_se_propage():
    """Le trou ne suffit pas : l'operation suivante bouge et emporte son voisin.

    J1 : op1[100-150] puis op2[160-210] sur M2 — un trou de 10 unites seulement,
    face a 50 de retard. W2, juste derriere op2, est donc atteint.
    """
    schedule, instance = _atelier([100, 160], [("W2", "M2", 210)])
    zone = _analyse(schedule, instance)

    assert zone.impacted_job_ids == {"J1", "W2"}
    assert zone.reason_by_job["W2"] == REASON_CONTENTION, (
        "W2 est atteint par la contention depuis op2, la precedence ne sortant "
        "jamais de son propre job"
    )


def test_la_portee_reste_bornee_aux_operations_dun_seul_job():
    """Invariant conserve : la precedence ne sort JAMAIS du job dont elle part.

    Les temoins sont ici sur une machine M9 que J1 n'utilise pas. Meme avec un retard
    enorme et aucune absorption possible, la precedence ne peut pas les atteindre —
    seule la contention le pourrait, et J1 ne partage aucune machine avec eux.
    """
    schedule, instance = _atelier(
        [100, 160, 220], [("W1", "M9", 100), ("W2", "M9", 400)]
    )
    zone = _analyse(schedule, instance, _allonge_op1(900))

    assert zone.impacted_job_ids == {"J1"}


# ==========================================================================
# Regle de separation : le trou se mesure sur l'OPERATION, pas l'occupation
# ==========================================================================
def test_le_setup_dun_tiers_ne_reduit_pas_labsorption_du_job():
    """Le trou de precedence ignore le setup, qui releve de la contention machine.

    J1 : op1[100-150] puis op2[400-450], soit 250 unites de trou. L'operation 2 porte
    un setup de 220 unites venant d'un TIERS (JX) sur M2 : son occupation commence
    donc des 180.

    Mesure sur l'OCCUPATION, le trou tomberait a 30 et le retard de 50 se propagerait
    jusqu'a W2. Mesure sur l'OPERATION — la regle retenue —, le trou vaut 250 et le
    retard est absorbe.

    Ce test fige la separation : la precedence d'un job ne doit pas dependre d'un
    setup que lui impose un tiers sur sa machine.
    """
    entries = [
        _entry("J1", "M1", 1, 100, 50),
        _entry("J1", "M2", 2, 400, 50,
               setup=SetupEntry(from_job_id="JX", start_time=180,
                                end_time=400, duration=220)),
        _entry("W2", "M2", 1, 450, 50),
    ]
    jobs = [
        Job(id="J1",
            operations=[Operation("J1", "M1", 50, 1), Operation("J1", "M2", 50, 2)],
            deadline=9000, weight=1.0),
        Job(id="W2", operations=[Operation("W2", "M2", 50, 1)],
            deadline=9000, weight=1.0),
    ]
    instance = ProblemInstance(jobs=jobs, machines=["M1", "M2"],
                               setup_times={}, wr=1)
    zone = _analyse(Schedule(entries=entries), instance)

    assert zone.impacted_job_ids == {"J1"}, (
        "le setup d'un tiers ne doit pas rendre la precedence de J1 moins absorbante"
    )


# ==========================================================================
# La precedence reste hors du signal de troncature (exclusion DEFINITIVE, D14)
# ==========================================================================
def test_une_coupe_de_precedence_ne_contribue_jamais_au_signal():
    """Exclusion definitive, pour une raison de GRANULARITE (cf. D14).

    `max_impacted_jobs_fraction` opere par JOB, tandis que la precedence reste a
    l'interieur des operations d'un job deja marque, que la zone retient en
    totalite. Une coupe de precedence ne peut donc jamais faire perdre
    d'information, quelle que soit la position de l'horizon.

    Les operations sont ici BOUT A BOUT — op1[100-150], op2[150-200], op3[200-250] —
    pour qu'aucun temps mort n'absorbe le retard : la cascade progresse donc vraiment
    quand l'horizon la coupe. Avec T_now = 50 et un horizon de 120, la borne tombe a
    170 : op2 passe, op3 est coupee.
    """
    schedule, instance = _atelier([100, 150, 200], [])
    zone = _analyse(schedule, instance, search_horizon=120)

    assert zone.horizon_end == 170
    assert zone.truncated is True, "l'horizon coupe bien la propagation"
    assert zone.truncated_before_convergence is False, (
        "mais rien n'est perdu : la precedence est exclue du signal"
    )
    positions = {e.position_in_job for e in zone.impacted_entries if e.job_id == "J1"}
    assert positions == {1, 2, 3}, (
        "toutes les operations du job restent dans la zone, horizon ou pas"
    )
