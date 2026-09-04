"""
Scenarios synthetiques des jonctions zone / futur non touche.

Source de verite unique pour les scenarios du livrable 1 de la Discussion 2 :
`tests/test_incremental_jonctions.py` les consomme comme fixtures, et
`tests/validate_incremental.py` les rejoue tels quels. Les definir ici evite que le
script de validation et la suite de tests divergent silencieusement.

Chaque constructeur renvoie un triplet `(Schedule, ProblemInstance, PerturbationEvent)`
directement exploitable par `resolve_incremental`.

Les scenarios sont DETERMINISTES : c'est la geometrie du planning, et non un alea de
CP-SAT, qui force le placement recherche.
"""
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.perturbation import make_event
from scheduling.models.schedule import Schedule, ScheduleEntry, SetupEntry

T_NOW = 50


def _entry(job_id, machine_id, position, start, duration, setup=None):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine_id, position_in_job=position,
        start_time=start, end_time=start + duration, duration=duration, setup=setup,
    )


def _event_j3(new_duration=60):
    """Met J3 dans la zone. La duree n'est qu'un vehicule pour l'evenement."""
    return make_event("duration_change", timestamp=T_NOW, job_id="J3",
                      position_in_job=1, machine_id="M1",
                      new_duration=new_duration)


def zone_derriere_une_non_touchee():
    """Constat B : une operation de zone qui veut se coller derriere une non touchee.

    M1 : J1[100-150] non touchee, puis J3 (zone) avec deadline serree et poids fort,
    donc tout interet a s'avancer au maximum. Le setup entrant J1 -> J3 vaut 40,
    volontairement gros.

    J3 ne peut pas passer AVANT J1 : il ne reste que 50 unites entre T_now et le
    debut de J1, pour une operation de 60.
    """
    entries = [
        _entry("J1", "M1", 1, 100, 50),
        _entry("J3", "M1", 1, 300, 60),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1)],
            deadline=900, weight=1.0),
        Job(id="J3", operations=[Operation("J3", "M1", 60, 1)],
            deadline=160, weight=50.0),
    ]
    setup_times = {("J1", "J3", "M1"): 40, ("J3", "J1", "M1"): 12}
    instance = ProblemInstance(jobs=jobs, machines=["M1"],
                               setup_times=setup_times, wr=1)
    return Schedule(entries=entries), instance, _event_j3()


def zone_derriere_une_non_touchee_non_jonction():
    """Constat B, variante : la non touchee visee n'est pas celle de jonction.

    M1 : J0[60-90] (jonction), J1[100-150] (non touchee ordinaire), puis J3 de la
    zone qui veut se coller derriere J1.
    """
    entries = [
        _entry("J0", "M1", 1, 60, 30),
        _entry("J1", "M1", 1, 100, 50),
        _entry("J3", "M1", 1, 300, 60),
    ]
    jobs = [
        Job(id="J0", operations=[Operation("J0", "M1", 30, 1)], deadline=900, weight=1.0),
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1)], deadline=900, weight=1.0),
        Job(id="J3", operations=[Operation("J3", "M1", 60, 1)], deadline=160, weight=50.0),
    ]
    setup_times = {
        ("J1", "J3", "M1"): 40, ("J0", "J3", "M1"): 40,
        ("J0", "J1", "M1"): 5, ("J1", "J0", "M1"): 5,
        ("J3", "J1", "M1"): 12, ("J3", "J0", "M1"): 5,
    }
    instance = ProblemInstance(jobs=jobs, machines=["M1"],
                               setup_times=setup_times, wr=1)
    return Schedule(entries=entries), instance, _event_j3()


def zone_encadree_par_deux_non_touchees():
    """Les deux sens de transition en une seule machine.

    M1 : J1[100-150] non touchee, J3[200-260] zone, J2[400-450] non touchee.
    Les deux transitions exigent un setup non nul : celle en aval de J1 releve de la
    garde aval (D10), celle en amont de J2 de la garde amont preexistante.
    """
    entries = [
        _entry("J1", "M1", 1, 100, 50),
        _entry("J3", "M1", 1, 200, 60),
        _entry("J2", "M1", 1, 400, 50,
               setup=SetupEntry(from_job_id="J1", start_time=380,
                                end_time=400, duration=20)),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1)], deadline=900, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1)], deadline=900, weight=1.0),
        Job(id="J3", operations=[Operation("J3", "M1", 60, 1)], deadline=160, weight=50.0),
    ]
    setup_times = {
        ("J1", "J3", "M1"): 25,  # transition AVAL de J1
        ("J3", "J2", "M1"): 30,  # transition AMONT de J2
        ("J1", "J2", "M1"): 20,
        ("J2", "J3", "M1"): 15, ("J2", "J1", "M1"): 12, ("J3", "J1", "M1"): 12,
    }
    instance = ProblemInstance(jobs=jobs, machines=["M1"],
                               setup_times=setup_times, wr=1)
    return Schedule(entries=entries), instance, _event_j3()


def zone_intercalee_entre_deux_non_touchees():
    """Constat A : la limite connue de D8, confirmee benigne.

    Identique au precedent quant a la forme, mais J3 a une deadline lache : la zone
    reste a sa place au lieu de se coller, et c'est la metadonnee perimee de J2 qui
    est observee (elle nomme J1 alors que J3 la precede desormais).
    """
    entries = [
        _entry("J1", "M1", 1, 100, 50),
        _entry("J3", "M1", 1, 200, 60),
        _entry("J2", "M1", 1, 400, 50,
               setup=SetupEntry(from_job_id="J1", start_time=380,
                                end_time=400, duration=20)),
    ]
    jobs = [
        Job(id="J1", operations=[Operation("J1", "M1", 50, 1)], deadline=900, weight=1.0),
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1)], deadline=900, weight=1.0),
        Job(id="J3", operations=[Operation("J3", "M1", 60, 1)], deadline=900, weight=1.0),
    ]
    setup_times = {
        ("J1", "J2", "M1"): 20,  # setup d'origine porte par J2
        ("J3", "J2", "M1"): 30,  # setup reellement en vigueur apres fusion
        ("J1", "J3", "M1"): 10,
        ("J2", "J3", "M1"): 15, ("J2", "J1", "M1"): 12, ("J3", "J1", "M1"): 12,
    }
    instance = ProblemInstance(jobs=jobs, machines=["M1"],
                               setup_times=setup_times, wr=1)
    return Schedule(entries=entries), instance, _event_j3(new_duration=90)


def zone_devant_la_jonction():
    """Cas ou un setup de jonction est REELLEMENT emis (cf. D8).

    M1 : J3 (zone) puis J2[400-450], premiere entree non touchee de la machine donc
    entree de jonction. Comme la zone precede la jonction, son setup redevient une
    variable du modele et un SetupEntry est emis avec des dates issues du solveur.

    Le trou de 240 unites laisse largement la place au setup J3 -> J2 (30 unites) :
    le placement est contraint par le modele, pas par l'espace disponible.
    """
    entries = [
        _entry("J3", "M1", 1, 100, 60),
        _entry("J2", "M1", 1, 400, 50,
               setup=SetupEntry(from_job_id="J9", start_time=370,
                                end_time=400, duration=30)),
    ]
    jobs = [
        Job(id="J2", operations=[Operation("J2", "M1", 50, 1)], deadline=900, weight=1.0),
        Job(id="J3", operations=[Operation("J3", "M1", 60, 1)], deadline=900, weight=1.0),
    ]
    setup_times = {("J3", "J2", "M1"): 30, ("J2", "J3", "M1"): 15}
    instance = ProblemInstance(jobs=jobs, machines=["M1"],
                               setup_times=setup_times, wr=1)
    return Schedule(entries=entries), instance, _event_j3()


# Nom lisible -> constructeur, pour les parcours automatiques (script de validation).
SCENARIOS = {
    "zone derriere une non touchee": zone_derriere_une_non_touchee,
    "zone derriere une non touchee (non jonction)":
        zone_derriere_une_non_touchee_non_jonction,
    "zone encadree par deux non touchees": zone_encadree_par_deux_non_touchees,
    "zone intercalee (limite benigne D8)": zone_intercalee_entre_deux_non_touchees,
    "zone devant la jonction (setup emis)": zone_devant_la_jonction,
}
