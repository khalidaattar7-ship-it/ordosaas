# OrdoSaaS — Contexte et décisions du projet

> Fichier vivant. Il est mis à jour **au moment** où une décision ou une hypothèse est
> prise, pas en fin de session. En cas de conflit factuel avec un prompt de session,
> c'est ce fichier qui fait foi sur l'état réel du code.

## État actuel

*(dernière mise à jour : 2026-09-03, début de la Discussion 1)*

### Dépôt et arborescence

- Dépôt distant : `https://github.com/khalidaattar7-ship-it/ordosaas` — accès lecture **et**
  écriture vérifiés le 2026-09-03 (`git ls-remote` + `git push --dry-run`).
- **Particularité importante du clone local** : la racine du dépôt git est le répertoire
  personnel `C:\Users\AATTAR Rayhane\`, et le projet est suivi sous le sous-dossier
  `ordosaas/`. Le dépôt distant a la même forme (racine = `.dockerignore`, `Dockerfile`,
  `ordosaas/`, `railway.json`, `render.yaml`). Conséquence : tous les fichiers personnels
  du répertoire utilisateur (`Desktop/`, `Documents/`, `AppData/`, `.claude.json`,
  `NTUSER.DAT`, …) apparaissent comme non suivis dans ce dépôt. **Ne jamais utiliser
  `git add -A` / `git add .`** — toujours ajouter les chemins explicitement.
- Branche locale : `master`. Branche par défaut distante : `main`.

### Service de scheduling (`ordosaas/backend/scheduling/`) — existant et fonctionnel

Modèles (`models/`) :
- `job.py` : `Operation(job_id, machine_id, duration, position)`,
  `Job(id, operations, deadline, weight)`,
  `ProblemInstance(jobs, machines, setup_times, wr)` + `get_setup()`, `horizon`.
- `schedule.py` : `SetupEntry(from_job_id, start_time, end_time, duration)`,
  `ScheduleEntry(job_id, machine_id, position_in_job, start_time, end_time, duration, setup)`,
  `JobResult(...)`, `Schedule(entries, jobs_result, total_weighted_tardiness, method_used,
  solver_status, atcs_twt, improvement_vs_atcs_pct, exit_context)` + `compute_kpis(jobs)`
  et les propriétés dérivées (`nb_jobs_late`, `horizon`, `total_setup_time`, …).
- `window.py` : `Window(index, t_start, t_end, jobs)`,
  `WindowResult(window, schedule, exit_context, objective, method, duration_seconds,
  recursion_depth)`.
- `context.py` : `BoundaryContext(last_job_per_machine, active_setups, pending_jobs,
  machine_loads, incomplete_jobs)` + `BoundaryContext.empty()`.

Solveurs (`solvers/`) :
- `base.py` : `BaseSolver.solve(instance) -> Schedule`.
- `atcs_solver.py` : `ATCSSolver`.
- `cpsat_solver.py` : `CPSATSolver(timeout_seconds=30)` avec
  `solve(instance)` et `solve_with_context(instance, left_context, right_context)`.
- `lns_recursive.py` : `LNSRecursiveSolver` (orchestrateur des 4 phases).

Composants (`components/`) : `window_manager.py`, `context_propagator.py`,
`inter_window_optimizer.py`. Plus `dispatcher.py` (`SolverDispatcher`).

Instance d'exemple : `ordosaas/backend/tests/fixtures/{jobs,operations,setups}.csv`
— 10 jobs (J1..J10), 3 machines (M1, M2, M3), 3 opérations par job, **WR = 2**
(la valeur `wr=2` est fixée dans `tests/validate_example.py`, pas dans les CSV).

## Décisions prises

### D1 — Accès au dépôt distant rétabli (2026-09-03)

Le remote `origin` n'était pas configuré dans le clone local et github.com était
injoignable. Khalid a rendu le dépôt public ; `origin` a été ajouté, l'accès lecture et
écriture est vérifié (`git ls-remote` OK, `git push --dry-run` rejeté uniquement en
non-fast-forward, donc authentifié). La branche locale `master` était **en retard de 2
commits** sur `origin/main` (`ebf89bd`, `0b74200`) ; les modifications non commitées de
l'arbre de travail étaient exactement le contenu de ces 2 commits (poussés depuis ailleurs).
`master` a été mis à jour en fast-forward sur `origin/main`. Deux modifications locales
sans rapport avec cette session (`backend/requirements.txt`, `frontend/Dockerfile`) sont
laissées non commitées et intactes.

### D2 — `IncrementalOptimizer` utilise un modèle CP-SAT dédié (2026-09-03) — résout H1

Décision de Khalid : ne pas étendre `CPSATSolver.solve_with_context` et ne pas réutiliser
`LNSRecursiveSolver._optimize_window_recursive`. Justification : `solve_with_context`
traite le contexte droit comme **approximatif et purement informationnel** (cohérent avec
le LNS initial, où il vient d'ATCS — et de fait le paramètre `right_context` y est
aujourd'hui accepté mais jamais utilisé dans le modèle), alors que l'incrémental a besoin
d'un contexte droit **exact et contraignant** (le planning futur déjà optimisé). Ce sont
deux sémantiques différentes, pas deux jeux de paramètres — d'où un modèle CP-SAT séparé,
qui évite en outre toute régression sur le solveur initial.

### D3 — Le validateur canonique vit dans `scheduling/validation.py` (2026-09-03) — résout H2

Décision de Khalid : les dataclasses du projet sont des contrats de données purs ; la
logique de validation appartient aux composants, pas aux modèles — cohérent avec le
découpage déjà en place (`components/`). Le module `scheduling/validation.py` devient le
seul endroit de vérité pour la validité d'un `Schedule` (précédence, NoOverlap
opérations + setups, Cumulative WR), et unifie les deux copies existantes
(`tests/conftest.py::assert_no_machine_overlap`, `tests/validate_example.py::validate_no_overlap`).

Vérification demandée et faite : **`InterWindowOptimizer` ne contient aucune vérification
de non-chevauchement** à migrer. Ses seules méthodes sont `optimize`,
`_compute_junction_costs`, `_optimize_junction`, `_assemble_schedule`,
`_recompute_window_kpis`, `_build_applied`, `_assemble_from_mixed`, `_apply_new_results`.
`_compute_junction_costs` mesure un *coût* de jonction (setup non absorbé + retard
pondéré), pas une validité. Il n'y a donc bien que deux copies à unifier, toutes deux
côté tests.

### D4 — Emplacement des nouveaux fichiers (2026-09-03)

Suit le découpage existant `models/` / `solvers/` / `components/` :
- `models/perturbation.py` — `PerturbationEvent` (donnée pure)
- `components/schedule_state_manager.py` — `ScheduleStateManager`
- `components/impact_analyzer.py` — `ImpactAnalyzer`, `ImpactZone`
- `components/incremental_context_builder.py` — `IncrementalContextBuilder`
- `components/schedule_merger.py` — `ScheduleMerger`
- `solvers/incremental_optimizer.py` — `IncrementalOptimizer` (modèle CP-SAT dédié, cf. D2)
- `validation.py` — validateur canonique (cf. D3)

### D5 — `PerturbationEvent` est une dataclass Python pure (2026-09-03) — résout H3

Décision de Khalid : aucune dépendance BDD dans cette session. Les 5 types
(`machine_breakdown`, `urgent_job`, `duration_change`, `job_cancel`, `resource_change`)
viennent du document de conception `docs/architecture-incremental.md` §2.7, uniquement
pour garder une terminologie cohérente en vue de la Discussion 4. **Aucune migration ni
table n'est créée maintenant** — c'est explicitement hors périmètre.

### D6 — Écarts assumés par rapport à `ContextPropagator` (2026-09-03)

`IncrementalContextBuilder` réutilise `ContextPropagator.build_left_context()` et
`build_right_context()` telles quelles pour tout le calcul commun (`last_job_per_machine`,
`machine_loads`, `pending_jobs`, `incomplete_jobs`). Deux écarts sont nécessaires, et
justifiés **avant** d'être écrits, comme le demande le prompt :

**Écart 1 — le contexte droit est EXACT, plus approximatif.** La docstring de
`ContextPropagator` pose comme « règle fondamentale » que le contexte droit est *toujours*
approximatif, car il vient du planning ATCS. C'est vrai du LNS initial, pas de
l'incrémental : ici le futur non touché vient de la résolution précédente **déjà
optimisée**, il est simplement non retouché (cf. §2.1). `build_right_context()` est donc
appelée en lui passant le `Schedule` réel au lieu du `Schedule` ATCS — le calcul est
identique, seule la nature de l'entrée change. `ContextPropagator` n'est pas modifiée,
pour ne pas toucher au LNS initial.

**Écart 2 — le contexte droit porte des `machine_loads`.** `build_right_context()` renvoie
`machine_loads={}` : dans le LNS initial le contexte droit est purement informationnel, il
ne contraint rien (et de fait `CPSATSolver.solve_with_context` ignore complètement son
`right_context`, cf. D2). Dans l'incrémental, le contexte droit doit **contraindre** : la
zone réoptimisée ne peut pas déborder sur la première opération non touchée de chaque
machine. `IncrementalContextBuilder` enrichit donc le contexte droit avec
`machine_loads = {machine_id: début de la première entrée future non touchée}`, à lire
comme une **date au plus tard** pour la zone, et non comme une charge déjà consommée
(sens qu'a le champ dans le contexte gauche). Ce double sens du champ selon le côté est
assumé pour ne pas modifier la dataclass `BoundaryContext` partagée avec le LNS.

**Ajout — `active_setups` du contexte gauche.** `ContextPropagator` renvoie toujours
`active_setups=[]`. L'incrémental les remplit réellement : un setup figé qui chevauche
T_now consomme un technicien au-delà de T_now et doit compter dans la contrainte
Cumulative WR de la zone. Le champ existe déjà dans `BoundaryContext` et
`CPSATSolver.solve_with_context` sait déjà le consommer — c'est un remplissage, pas un
écart de structure.

## Hypothèses en attente de validation par Khalid

### H4 — Le `schema_bdd.sql` de référence est un document de conception (2026-09-03)

Le schéma SQL de l'annexe (§2.7) est une intention de conception, pas forcément le reflet
exact de ce qui est — ou sera — implémenté en SQLAlchemy dans ce dépôt. Avant
d'implémenter la migration réelle en **Discussion 4**, il faudra vérifier si les modèles
SQLAlchemy existants pour `resolutions` définissent déjà des conventions de nommage
différentes, et les concilier avec les 5 valeurs de type retenues ici pour
`PerturbationEvent`.

### H5 — Le routage du garde-fou de repli reste à faire (2026-09-03)

Conformément au point 7 du prompt, le garde-fou de dépassement de seuil est **détecté et
signalé**, mais le routage réel vers `LNSRecursiveSolver` dans `SolverDispatcher` n'est
**pas** implémenté. C'est un travail explicitement laissé pour une session ultérieure.

Le point d'extension livré, dans `scheduling/components/impact_analyzer.py` :

- `ImpactAnalyzer(fallback_threshold=0.5)` — seuil configurable, validé dans `]0, 1]` ;
- `ImpactZone.fallback_recommended` — drapeau posé par `analyze()`, accompagné d'un
  `logger.warning` ; `analyze()` ne lève jamais d'elle-même, l'appelant reste maître ;
- `ImpactAnalyzer.is_suitable(zone)` / `check_suitability(zone)` ;
- `IncrementalNotSuitableError(zone, threshold)` — exception dédiée, qui porte la zone et
  le seuil et dont la docstring décrit le contrat attendu du futur appelant : rattraper et
  relancer une résolution complète, plutôt que forcer une résolution partielle dégradée.

`tests/test_fallback_guard.py::test_le_dispatcher_ne_route_pas_encore_vers_lincremental`
verrouille l'absence de routage : si ce test tombe un jour, c'est que le branchement a été
fait, et il faudra retirer cette hypothèse H5 plutôt que contourner le test.

### H6 — Unité de temps et valeurs par défaut de l'horizon de recherche (2026-09-03)

Les `start_time` / `end_time` / `duration` du projet sont des entiers sans unité
explicite nulle part dans le code. En supposant la **minute** (cohérent avec les durées
de l'instance d'exemple, 4 à 82 par opération), les valeurs par défaut de `ImpactAnalyzer`
ont été fixées à `search_horizon = 240` (les 4 prochaines heures, cf. §2.4) et
`max_impacted_jobs = 30` (les 30 prochains jobs, cf. §2.4). Ce sont des **défauts de
constructeur, surchargeables à chaque appel** — rien n'est codé en dur dans la logique.
Si l'unité réelle n'est pas la minute, seuls ces deux défauts sont à revoir.

Note de conception : la borne de l'horizon est **inclusive** — une opération démarrant
exactement à `T_now + search_horizon` reste dans la zone.

## Prochaines étapes prévues

Plan global à 5 discussions :

| # | Sujet | État |
|---|---|---|
| 1 | Composants algorithmiques du réordonnancement incrémental | **en cours** |
| 2 | Scénarios de test approfondis + script de validation dédié | à venir |
| 3 | Worker asynchrone (Redis / RQ) | à venir |
| 4 | Endpoints API (`POST /resolutions/{id}/events`, `GET /resolutions/{id}/diff`) + migrations Alembic | à venir |
| 5 | Déploiement | à venir |

Composants à livrer dans la Discussion 1, dans l'ordre (un commit poussé par composant) :

1. `PerturbationEvent` — à faire
2. `ScheduleStateManager` — à faire
3. `ImpactAnalyzer` — à faire
4. `IncrementalContextBuilder` — à faire
5. `IncrementalOptimizer` (+ terme de stabilité, `STABILITY_WEIGHT` = 0.1) — à faire
6. `ScheduleMerger` — à faire
7. Garde-fou de repli (documenté, non routé) — à faire
8. 3-4 scénarios de test minimaux sur l'instance d'exemple 10 jobs — à faire
