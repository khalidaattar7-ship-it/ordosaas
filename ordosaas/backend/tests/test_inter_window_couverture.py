"""Couverture d'`InterWindowOptimizer` : Link State, assemblage, convergence.

Complete les tests de D18, qui ne couvraient que `_optimize_junction`. Les trois zones
traitees ici avaient ete nommees comme nues en D18 ; la cartographie du 2026-09-18 a
montre qu'`optimize()` lui-meme, le point d'entree public, ne l'etait pas moins.

AUCUN de ces tests n'appelle CP-SAT. Le cout de jonction et l'assemblage sont du calcul
pur, et la boucle de convergence est exercee avec un `_optimize_junction` substitue. Ils
sont donc rapides et DETERMINISTES par construction — la regle posee en D19 pour les
tests de garde-fou, ici obtenue sans avoir a configurer un solveur.

La specification faisant autorite est `PFA_Descriptif_Technique_MVP_v2.docx`, Phase 4 :

    Sous-phase Link State — les aretes sont les couts de jonction (setups
    inter-fenetres, violations WR, retard propage). Les frontieres les plus couteuses
    sont identifiees et classees par priorite.

    Sous-phase Distance Vector cible — le processus itere jusqu'a convergence
    (amelioration < epsilon) ou atteinte d'un nombre maximal d'iterations
    (MAX_ITERATIONS = 5).
"""
import pytest

from scheduling.components.inter_window_optimizer import InterWindowOptimizer
from scheduling.models.context import BoundaryContext
from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.models.schedule import Schedule, ScheduleEntry, SetupEntry
from scheduling.models.window import Window, WindowResult

DUREE = 10


def _op(job_id, machine="M1"):
    return Operation(job_id, machine, DUREE, 1)


def _entry(job_id, start, machine="M1", setup=None):
    return ScheduleEntry(
        job_id=job_id, machine_id=machine, position_in_job=1,
        start_time=start, end_time=start + DUREE, duration=DUREE, setup=setup,
    )


def _fenetre(index, noms, jobs, debuts, machine="M1", deadline=500):
    schedule = Schedule(
        entries=[_entry(j, d, machine) for j, d in zip(noms, debuts)],
        method_used="cpsat",
    )
    for job_id, debut in zip(noms, debuts):
        fin = debut + DUREE
        retard = max(0, fin - deadline)
        schedule.jobs_result.append(
            __import__("scheduling.models.schedule", fromlist=["JobResult"]).JobResult(
                job_id=job_id, deadline=deadline, weight=1.0, completion_time=fin,
                tardiness=retard, is_late=retard > 0, weighted_tardiness=float(retard),
            )
        )
    return WindowResult(
        window=Window(index=index, t_start=min(debuts), t_end=max(debuts) + DUREE,
                      jobs=[jobs[j] for j in noms]),
        schedule=schedule, exit_context=BoundaryContext.empty(),
        objective=0.0, method="cpsat",
    )


def _optimiseur():
    return InterWindowOptimizer(cpsat_solver=None, junction_radius=2)


# ==========================================================================
# Livrable 2 — `_compute_junction_costs` (sous-phase Link State)
# ==========================================================================
def _deux_fenetres(setup_ab, ecart, deadline=500):
    """A dans la fenetre 0, B dans la fenetre 1, separes par `ecart` unites."""
    jobs = {j: Job(id=j, operations=[_op(j)], deadline=deadline, weight=1.0)
            for j in ("A", "B")}
    instance = ProblemInstance(
        jobs=list(jobs.values()), machines=["M1"],
        setup_times={("A", "B", "M1"): setup_ab}, wr=2,
    )
    gauche = _fenetre(0, ["A"], jobs, [0], deadline=deadline)
    droite = _fenetre(1, ["B"], jobs, [DUREE + ecart], deadline=deadline)
    return instance, [gauche, droite]


def test_le_cout_reflete_un_setup_inter_fenetres_non_couvert():
    """Setup de 20 du, seulement 5 d'ecart laisse : il manque 15."""
    instance, fenetres = _deux_fenetres(setup_ab=20, ecart=5)
    couts = _optimiseur()._compute_junction_costs(fenetres, instance)
    assert len(couts) == 1
    assert couts[0]["index"] == 0
    assert couts[0]["cost"] == pytest.approx(15)


def test_un_setup_entierement_couvert_par_lecart_ne_coute_rien():
    """Setup de 20 du, 30 d'ecart : la frontiere n'a rien a reoptimiser."""
    instance, fenetres = _deux_fenetres(setup_ab=20, ecart=30)
    assert _optimiseur()._compute_junction_costs(fenetres, instance) == []


def test_deux_fenetres_sans_interaction_sont_ABSENTES_et_non_a_cout_nul():
    """Comportement voulu, verifie et pas suppose : la jonction est OMISE.

    Le code n'ajoute une entree que `if boundary_cost > 0`. C'est coherent avec la
    specification, qui parle d'identifier « les frontieres les plus couteuses » : une
    frontiere sans cout n'a pas a entrer dans le graphe d'interactions.
    """
    instance, fenetres = _deux_fenetres(setup_ab=0, ecart=5)
    couts = _optimiseur()._compute_junction_costs(fenetres, instance)
    assert couts == [], "une frontiere sans cout ne doit pas figurer dans le graphe"


def test_le_retard_de_la_fenetre_droite_entre_dans_le_cout():
    """Second terme du cout : le retard, pondere par 0.1.

    ECART SIGNALE : la specification parle de « retard propage ». Le code compte le
    retard de TOUS les jobs en retard de la fenetre droite, lie ou non a la jonction,
    et le facteur 0.1 n'apparait pas dans la specification. Ce test verrouille le
    comportement REEL, sans le presenter comme conforme.
    """
    instance, fenetres = _deux_fenetres(setup_ab=0, ecart=5, deadline=10)
    couts = _optimiseur()._compute_junction_costs(fenetres, instance)
    assert len(couts) == 1
    # B finit a 25 pour une echeance de 10 : retard 15, pondere 0.1 -> 1.5
    assert couts[0]["cost"] == pytest.approx(1.5)


def test_les_violations_wr_nentrent_PAS_dans_le_cout():
    """ECART ASSUME entre la specification et le code, verrouille comme tel.

    La specification nomme TROIS composantes d'arete : setups inter-fenetres,
    violations WR, retard propage. Le code n'en implemente que deux. Une frontiere
    couteuse UNIQUEMENT par contention WR n'est donc jamais identifiee, donc jamais
    reoptimisee.

    Ce test documente l'etat reel. Il devra etre inverse le jour ou la troisieme
    composante sera implementee.
    """
    jobs = {j: Job(id=j, operations=[_op(j)], deadline=500, weight=1.0)
            for j in ("A", "B")}
    instance = ProblemInstance(
        jobs=list(jobs.values()), machines=["M1", "M2"], setup_times={}, wr=1,
    )
    # Deux setups simultanes sur des machines differentes, pour WR=1 : une violation
    # franche, que le cout de jonction ignore pourtant.
    gauche = _fenetre(0, ["A"], jobs, [0])
    gauche.schedule.entries.append(ScheduleEntry(
        job_id="A", machine_id="M2", position_in_job=2, start_time=0, end_time=10,
        duration=10, setup=SetupEntry(from_job_id="Z", start_time=0, end_time=5,
                                      duration=5),
    ))
    droite = _fenetre(1, ["B"], jobs, [2])
    droite.schedule.entries[0].setup = SetupEntry(
        from_job_id="Y", start_time=0, end_time=5, duration=5,
    )
    couts = _optimiseur()._compute_junction_costs([gauche, droite], instance)
    assert couts == [], (
        "si ce test echoue, la composante WR du cout de jonction a ete implementee : "
        "mettre a jour la cartographie et inverser cette assertion"
    )


def test_une_fenetre_vide_sur_une_machine_est_ignoree_sans_erreur():
    """Cas de bord : la machine n'est occupee que d'un cote de la frontiere."""
    jobs = {j: Job(id=j, operations=[_op(j, "M1")], deadline=500, weight=1.0)
            for j in ("A", "B")}
    instance = ProblemInstance(
        jobs=list(jobs.values()), machines=["M1", "M2"],
        setup_times={("A", "B", "M2"): 50}, wr=2,
    )
    gauche = _fenetre(0, ["A"], jobs, [0])
    droite = _fenetre(1, ["B"], jobs, [15])
    # M2 n'a d'entree d'aucun cote : le setup de 50 declare sur M2 ne doit rien couter.
    assert _optimiseur()._compute_junction_costs([gauche, droite], instance) == []


def test_une_seule_fenetre_na_aucune_jonction():
    """Cas de bord : pas de frontiere du tout."""
    instance, fenetres = _deux_fenetres(setup_ab=20, ecart=0)
    assert _optimiseur()._compute_junction_costs(fenetres[:1], instance) == []


# ==========================================================================
# Livrable 3 — `_build_applied` (construction du resultat)
# ==========================================================================
@pytest.fixture
def trois_fenetres():
    noms = [["A1", "A2"], ["B1", "B2"], ["C1", "C2"]]
    jobs = {j: Job(id=j, operations=[_op(j)], deadline=500, weight=1.0)
            for g in noms for j in g}
    instance = ProblemInstance(
        jobs=list(jobs.values()), machines=["M1"], setup_times={}, wr=2,
    )
    fenetres = [_fenetre(i, g, jobs, [20 * i, 20 * i + DUREE])
                for i, g in enumerate(noms)]
    return instance, fenetres, jobs


def test_une_jonction_rejetee_nest_jamais_appliquee(trois_fenetres):
    """Les gardes H10a/b/c rejettent en renvoyant [] : rien ne doit etre applique."""
    instance, fenetres, _jobs = trois_fenetres
    avant = [[(e.job_id, e.start_time) for e in f.schedule.entries] for f in fenetres]
    applique = _optimiseur()._build_applied(fenetres, [])
    apres = [[(e.job_id, e.start_time) for e in f.schedule.entries] for f in applique]
    assert apres == avant


def test_un_index_hors_bornes_est_ignore_sans_rien_casser(trois_fenetres):
    """Garde `idx < 0 or idx + 1 >= len(applied)` : la jonction est sautee."""
    instance, fenetres, _jobs = trois_fenetres
    avant = [[(e.job_id, e.start_time) for e in f.schedule.entries] for f in fenetres]
    faux = [{"index": 99, "micro_schedule": Schedule(),
             "left_job_ids": {"A1"}, "right_job_ids": {"B1"}}]
    apres = [[(e.job_id, e.start_time) for e in f.schedule.entries]
             for f in _optimiseur()._build_applied(fenetres, faux)]
    assert apres == avant


def test_les_entrees_reoptimisees_remplacent_les_anciennes(trois_fenetres):
    """Le coeur de l'assemblage : substitution par identifiant de job."""
    instance, fenetres, _jobs = trois_fenetres
    micro = Schedule(entries=[_entry("A2", 500), _entry("B1", 520)])
    resultat = [{"index": 0, "micro_schedule": micro,
                 "left_job_ids": {"A2"}, "right_job_ids": {"B1"}}]
    applique = _optimiseur()._build_applied(fenetres, resultat)

    debuts_gauche = {e.job_id: e.start_time for e in applique[0].schedule.entries}
    debuts_droite = {e.job_id: e.start_time for e in applique[1].schedule.entries}
    assert debuts_gauche["A2"] == 500, "l'entree reoptimisee doit remplacer l'ancienne"
    assert debuts_gauche["A1"] == 0, "les jobs hors jonction ne bougent pas"
    assert debuts_droite["B1"] == 520
    assert debuts_droite["B2"] == 30


def test_lassemblage_ne_mute_pas_les_fenetres_dorigine(trois_fenetres):
    """`_clone_window_result` doit isoler : l'original reste intact.

    C'est ce qui permet a `optimize()` d'ESSAYER une jonction avant de l'accepter.
    Sans cette isolation, une jonction refusee laisserait quand meme sa trace.
    """
    instance, fenetres, _jobs = trois_fenetres
    micro = Schedule(entries=[_entry("A2", 500), _entry("B1", 520)])
    resultat = [{"index": 0, "micro_schedule": micro,
                 "left_job_ids": {"A2"}, "right_job_ids": {"B1"}}]
    _optimiseur()._build_applied(fenetres, resultat)

    origine = {e.job_id: e.start_time for e in fenetres[0].schedule.entries}
    assert origine["A2"] == DUREE, "la fenetre d'origine a ete mutee"
    assert fenetres[0].schedule.entries is not None


def test_les_kpi_de_fenetre_sont_recalcules_apres_substitution(trois_fenetres):
    """`_recompute_window_kpis` : le retard local doit suivre le deplacement."""
    instance, fenetres, _jobs = trois_fenetres
    micro = Schedule(entries=[_entry("A2", 1000), _entry("B1", 1020)])
    resultat = [{"index": 0, "micro_schedule": micro,
                 "left_job_ids": {"A2"}, "right_job_ids": {"B1"}}]
    applique = _optimiseur()._build_applied(fenetres, resultat)
    # A2 finit a 1010 pour une echeance de 500 : 510 de retard, poids 1.
    assert applique[0].schedule.total_weighted_tardiness == pytest.approx(510)
    assert applique[0].objective == applique[0].schedule.total_weighted_tardiness


# ==========================================================================
# Livrable 4 — critere de convergence
# ==========================================================================
class _JonctionFactice:
    """Substitut de `_optimize_junction` qui ameliore d'un facteur controle."""

    def __init__(self, facteur_amelioration):
        self.facteur = facteur_amelioration
        self.appels = 0

    def __call__(self, junction, window_results, instance):
        self.appels += 1
        return [{"index": junction["index"], "micro_schedule": Schedule(),
                 "left_job_ids": set(), "right_job_ids": set()}]


def _instance_a_jonction_couteuse():
    """Deux fenetres dont la frontiere coute toujours quelque chose."""
    jobs = {j: Job(id=j, operations=[_op(j)], deadline=500, weight=1.0)
            for j in ("A", "B")}
    instance = ProblemInstance(
        jobs=list(jobs.values()), machines=["M1"],
        setup_times={("A", "B", "M1"): 50}, wr=2,
    )
    gauche = _fenetre(0, ["A"], jobs, [0])
    droite = _fenetre(1, ["B"], jobs, [DUREE])  # ecart nul, setup 50 -> cout 50
    return instance, [gauche, droite]


def _optimiseur_avec_twt(monkeypatch, suite_twt, facteur=None):
    """Optimiseur dont l'assemblage renvoie des TWT imposes, dans l'ordre."""
    optim = InterWindowOptimizer(cpsat_solver=None, junction_radius=2, epsilon=0.01)
    faux = _JonctionFactice(facteur)
    monkeypatch.setattr(optim, "_optimize_junction", faux)

    valeurs = list(suite_twt)

    def faux_assemblage(window_results, instance):
        s = Schedule(method_used="lns")
        s.total_weighted_tardiness = valeurs.pop(0) if valeurs else valeurs_defaut[0]
        return s

    valeurs_defaut = [suite_twt[-1]]
    monkeypatch.setattr(optim, "_assemble_schedule", faux_assemblage)
    monkeypatch.setattr(
        optim, "_assemble_from_mixed",
        lambda wr, nr, inst: faux_assemblage(wr, inst),
    )
    return optim, faux


def test_la_boucle_sarrete_des_que_lamelioration_passe_sous_epsilon(monkeypatch):
    """Convergence AVANT MAX_ITERATIONS : une amelioration insuffisante arrete tout.

    TWT initial 1000, puis 999 propose : 0,1 % d'amelioration, sous les 1 % exiges.
    La jonction est refusee, `improved` reste faux, la boucle sort a la 1re iteration.
    """
    instance, fenetres = _instance_a_jonction_couteuse()
    optim, faux = _optimiseur_avec_twt(monkeypatch, [1000, 999, 999, 999, 999, 999])
    optim.optimize(fenetres, instance, Schedule())
    assert faux.appels == 1, (
        f"la boucle aurait du sortir apres la 1re iteration, {faux.appels} appels"
    )


def test_la_boucle_ne_depasse_jamais_max_iterations(monkeypatch):
    """Non-convergence : le processus s'arrete proprement au plafond.

    Chaque iteration ameliore de 50 %, donc `improved` reste vrai indefiniment. Seul
    MAX_ITERATIONS peut arreter la boucle — c'est le garde-fou de terminaison.
    """
    instance, fenetres = _instance_a_jonction_couteuse()
    suite = [1000] + [1000 / (2 ** i) for i in range(1, 40)]
    optim, faux = _optimiseur_avec_twt(monkeypatch, suite)
    assert optim.max_iterations == 5, "valeur par defaut attendue (specification)"
    optim.optimize(fenetres, instance, Schedule())
    assert faux.appels == 5, (
        f"exactement une jonction par iteration, plafonnee a 5 ; obtenu {faux.appels}"
    )


def test_le_seuil_depsilon_est_strict(monkeypatch):
    """Cas limite : une amelioration EXACTEMENT egale a epsilon est REFUSEE.

    Le test est `< current_twt * (1 - epsilon)`, une inegalite stricte. Avec
    epsilon = 0.01 et un TWT de 1000, le seuil vaut exactement 990 : proposer 990 ne
    suffit pas, il faut faire mieux.
    """
    instance, fenetres = _instance_a_jonction_couteuse()
    optim, faux = _optimiseur_avec_twt(monkeypatch, [1000] + [990] * 10)
    optim.optimize(fenetres, instance, Schedule())
    assert faux.appels == 1, "990 est le seuil exact, il doit etre refuse"


def test_juste_sous_le_seuil_depsilon_est_accepte(monkeypatch):
    """Le pendant du precedent : 989,9 passe la ou 990 echoue.

    Sans cette paire, rien ne distinguerait une inegalite stricte d'une inegalite
    large — ni un epsilon mal applique.
    """
    instance, fenetres = _instance_a_jonction_couteuse()
    optim, faux = _optimiseur_avec_twt(monkeypatch, [1000] + [989.9] * 10)
    optim.optimize(fenetres, instance, Schedule())
    assert faux.appels > 1, "une amelioration superieure a epsilon doit etre acceptee"


def test_sans_jonction_couteuse_la_boucle_SORT_immediatement(monkeypatch):
    """`if not junction_costs: break` — et il faut verifier la SORTIE, pas l'inaction.

    Compter les jonctions reoptimisees ne suffit pas : sans le `break`, la boucle
    tournerait cinq fois a vide et le compteur resterait a zero. C'est le nombre
    d'appels au calcul de couts qui distingue une sortie d'un tour de roue inutile.
    """
    jobs = {j: Job(id=j, operations=[_op(j)], deadline=500, weight=1.0)
            for j in ("A", "B")}
    instance = ProblemInstance(
        jobs=list(jobs.values()), machines=["M1"], setup_times={}, wr=2,
    )
    fenetres = [_fenetre(0, ["A"], jobs, [0]), _fenetre(1, ["B"], jobs, [100])]
    optim, faux = _optimiseur_avec_twt(monkeypatch, [1000] * 10)

    calculs = []
    vrai_calcul = optim._compute_junction_costs
    monkeypatch.setattr(
        optim, "_compute_junction_costs",
        lambda wr, inst: (calculs.append(1), vrai_calcul(wr, inst))[1],
    )
    optim.optimize(fenetres, instance, Schedule())
    assert faux.appels == 0, "aucune jonction ne doit etre reoptimisee"
    assert len(calculs) == 1, (
        f"la boucle doit SORTIR au premier tour, pas tourner a vide "
        f"({len(calculs)} calculs de couts)"
    )
    # NOTE. Ce test ne distingue pas `if not junction_costs: break` de son absence :
    # sans lui, la boucle atteindrait `if not improved: break` au meme tour, avec le
    # meme resultat observable. C'est un MUTANT EQUIVALENT — ce `break` est un
    # court-circuit, pas un garde de comportement. Constate par test de mutation et
    # consigne ici plutot que masque par un test artificiel.


def test_une_seule_fenetre_court_circuite_toute_la_phase(monkeypatch):
    """`if len(window_results) <= 1` : rien a joindre, assemblage direct.

    Le resultat seul ne prouve rien — sans le court-circuit, la boucle produirait le
    meme planning apres un tour inutile. Ce qui distingue les deux, c'est que le
    calcul de couts ne doit JAMAIS etre invoque.
    """
    instance, fenetres = _instance_a_jonction_couteuse()
    optim = _optimiseur()
    calculs = []
    monkeypatch.setattr(
        optim, "_compute_junction_costs",
        lambda wr, inst: (calculs.append(1), [])[1],
    )
    resultat = optim.optimize(fenetres[:1], instance, Schedule())
    assert resultat.method_used == "lns"
    assert [e.job_id for e in resultat.entries] == ["A"]
    assert calculs == [], (
        "une fenetre unique ne doit declencher aucun calcul de cout de jonction"
    )
