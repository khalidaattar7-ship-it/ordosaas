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

### D7 — L'unité de temps du projet est ABSTRAITE ; les bornes deviennent relatives (2026-09-04) — résout H6

**Méthode : audit du code d'affichage, pas une question posée.** Le raisonnement est que
le formatage à l'affichage (labels d'axe, tooltips, conversion éventuelle en heures:minutes)
révèle l'unité que le backend est censé produire. L'audit a porté sur tout le chemin
d'affichage du diagramme de Gantt, puis sur l'ensemble du dépôt.

**Ce que l'audit a trouvé — vérifiable ligne à ligne :**

| Fichier / ligne | Constat |
|---|---|
| `frontend/src/components/gantt/GanttChart.jsx:49` | Libellé du zoom : `{zoom}px/u` — « pixels par **unité** », formulation volontairement agnostique |
| `frontend/src/components/gantt/GanttChart.jsx:27-32` | Pas des graduations : `10 / 25 / 50`, entiers bruts, aucun pas horaire |
| `frontend/src/components/gantt/GanttChart.jsx:62-70` | Les graduations sont rendues telles quelles (`{t}`), sans formatage h:mm |
| `frontend/src/components/gantt/GanttBar.jsx:3-4` | Tooltip : `${entry.start_time} → ${entry.end_time} (durée ${entry.duration})` — valeurs brutes, sans suffixe |
| `frontend/src/components/gantt/GanttBar.jsx:12-13` | Position et largeur = `start_time * zoom`, `duration * zoom` — multiplication directe, aucune conversion |
| `frontend/src/components/gantt/SetupBar.jsx:8-9` | Idem pour les setups |
| `frontend/src/pages/ResolutionDetail.jsx:163-173` | Les seuls `unit=` des KPI sont `"%"` et `"s"` ; le `"s"` porte sur `duration_seconds`, le **temps de calcul du solveur**, pas sur l'échelle du planning |
| `backend/app/models/{schedule_entry,job,operation}.py` | `Integer` nu ; aucun commentaire ni contrainte ne documente une unité |
| Balayage global du dépôt | Aucune occurrence de `* 60`, `/ 60` ni de « minute / heure » liée au planning. Les seuls résultats concernent l'expiration des tokens JWT (`ACCESS_TOKEN_EXPIRE_MINUTES`), sans rapport |

**Décision de Khalid, sur la base de cet audit : l'unité de temps est abstraite**, sans
signification physique. C'est cohérent avec les benchmarks académiques du domaine
(Avgerinos, Taillard), qui raisonnent en unités de temps abstraites, et avec
l'architecture multi-tenant où chaque usine fixe sa propre granularité à l'import.

**Conséquence appliquée dans le code — pas seulement documentée.** `search_horizon = 240`
et `max_impacted_jobs = 30` supposaient implicitement la minute (« 4 prochaines heures »,
« 30 prochains jobs », cf. §2.4). Elles sont remplacées par des **fractions relatives à
l'instance traitée**, dans `components/impact_analyzer.py` :

- `search_horizon_fraction = 0.15` — 15 % de l'horizon restant depuis T_now ;
- `max_impacted_jobs_fraction = 0.20` — 20 % des jobs futurs restants ;
- planchers, pour qu'une petite instance ne se retrouve pas avec une fenêtre quasi nulle :
  `min_impacted_jobs = 2` (le job perturbé plus un voisin de cascade) et, pour l'horizon,
  un plancher **lui-même sans unité** — la plus longue occupation future (setup compris),
  afin que la fenêtre puisse toujours contenir au moins une opération entière.
  `min_search_horizon` permet de forcer un plancher absolu si besoin.

Les fractions sont résolues **à chaque `analyze()`**, car elles dépendent du planning et de
T_now, pas seulement du constructeur ; les valeurs effectivement retenues sont tracées sur
la zone (`ImpactZone.search_horizon`, `ImpactZone.max_impacted_jobs`) et dans le log. Les
surcharges absolues `search_horizon=` / `max_impacted_jobs=` restent disponibles pour un
appelant qui sait ce qu'il fait, mais ce n'est plus le mode par défaut. Les anciennes
valeurs (240, 30) sont conservées **en commentaire** dans le code, pour tracer l'origine du
changement.

**Vérification des autres constantes du code incrémental** — aucune autre ne suppose une
unité physique implicite : `DEFAULT_STABILITY_WEIGHT = 0.1` est un poids sans dimension,
`WEIGHT_SCALE = 100` un facteur d'échelle entière, `DEFAULT_FALLBACK_THRESHOLD = 0.5` une
fraction, et `DEFAULT_TIMEOUT_SECONDS = 12` est en **secondes réelles de calcul CP-SAT**,
ce qui est légitime et sans rapport avec l'échelle du planning.

**Lien avec le constat sur les plannings compacts (voir plus bas).** Ce n'est plus
seulement une observation produit : elle est en partie corrigée. Sur l'instance d'exemple,
dont le planning résolu a un horizon de 674 sur 3 machines, l'ancien `search_horizon = 240`
couvrait environ la moitié du planning — la borne censée contenir un incident local ne
contenait plus rien, ce qui gonflait mécaniquement la cascade et sur-déclenchait le
garde-fou. Mesure faite à événement identique (T_now = 100, panne de 10 unités sur M1) :

| Bornes | Horizon | Max jobs | Jobs touchés | Repli |
|---|---|---|---|---|
| Anciennes (absolues 240 / 30) | 240 | 30 | 6 / 10 (60 %) | **déclenché** |
| Nouvelles (relatives 0.15 / 0.20) | 98 | 2 | 2 / 10 (20 %) | non déclenché |

L'incrémental redevient applicable là où il devait l'être. Ce comportement est verrouillé
par `tests/test_impact_analyzer.py::test_les_bornes_relatives_reduisent_le_sur_declenchement_du_repli`.
Le constat de fond reste valable — un planning optimisé au plus serré propage les retards —
mais il n'est plus aggravé par une borne mal dimensionnée.


### D8 — Les setups de jonction sont modélisés en variables, pas fabriqués après coup (2026-09-04) — résout H7

**Option retenue par Khalid** : modélisation explicite dans `IncrementalOptimizer`, avec
des variables optionnelles vers le premier job non touché de chaque machine. L'option
écartée — reconstruire les setups dans `ScheduleMerger` à partir du temps déjà réservé —
reproduirait exactement le bug déjà corrigé côté gauche plus tôt : une première version
fabriquait ces dates après coup à partir de `left.machine_loads`, et produisait 8
chevauchements sur l'instance réelle. **La règle tenue est qu'on n'émet jamais un
`SetupEntry` dont les dates ne sortent pas du modèle.**

**Ce qui change dans le modèle CP-SAT** (`solvers/incremental_optimizer.py`) :

1. `_build_untouched_obstacles` distingue désormais deux régimes. La **première** entrée
   non touchée d'une machine où la zone a des opérations est la *jonction* : son obstacle
   ne couvre plus que l'opération (`[start_time, end_time]`), la place de son setup étant
   libérée pour devenir une variable. Toutes les autres entrées non touchées gardent leur
   prédécesseur d'origine, donc leur obstacle couvre l'occupation complète et conserve
   l'élargissement conservateur vers l'amont, inchangé.
2. `_add_junction_setups` (nouveau) déclare, par machine de jonction, un intervalle
   **optionnel** par prédécesseur candidat de la zone, de durée `get_setup(job_zone,
   job_jonction, machine)`. Ces intervalles entrent dans le `NoOverlap` de la machine et
   dans la `Cumulative` WR, exactement comme les setups internes à la zone.
3. Le prédécesseur est **choisi par le modèle**, via `AddExactlyOne` sur les candidats de
   la zone plus une option « prédécesseur d'origine inchangé ». Le candidat retenu est
   contraint d'être l'opération de zone qui finit au plus tard avant la jonction
   (construction `fin_eff` / `dernier` / `AddMaxEquality`). Sans cette contrainte, CP-SAT
   désignerait un prédécesseur à setup nul et **économiserait un temps de setup qui doit
   pourtant être payé** — c'était le principal piège de cette modélisation.
4. Le setup d'origine de l'entrée de jonction devient lui aussi un intervalle optionnel,
   actif seulement si le prédécesseur d'origine subsiste : sans cela, deux setups
   occuperaient la machine devant la même opération.

**Remontée du résultat.** Ces setups précèdent une opération qui n'appartient pas à la
zone : ils ne peuvent donc pas être portés par le `Schedule` renvoyé, qui ne contient que
les entrées réoptimisées. Ils remontent par un nouveau champ
`WindowResult.junction_setups` — `{(job_id, position_in_job) de l'entrée non touchée →
SetupEntry}` — que `ScheduleMerger._apply_junction_setups` rattache à l'entrée visée. La
substitution passe par `dataclasses.replace` : les entrées non touchées appartiennent au
`Schedule` de la résolution précédente, que la fusion n'a aucune raison de muter. Le champ
a une valeur par défaut vide, donc le LNS initial, qui n'a pas de jonction de ce type,
n'est pas affecté.

**Vérification sur l'instance réelle** (10 jobs, setups non nuls). Balayage de 20
scénarios de panne (T_now de 60 à 350, sur les 3 machines) : les jonctions produisent
désormais de vrais `SetupEntry` — par exemple à T_now = 60 sur M2, trois setups émis
(`J5 → J10` : 304-324, 379-393, 457-463) — et `validate_schedule` renvoie **0 violation**
sur les 20 scénarios, frontières comprises. Avant D8, ces mêmes transitions n'étaient
portées par aucun `SetupEntry`.

**Limite résiduelle assumée.** Seule la **première** entrée non touchée de chaque machine
est traitée, conformément à l'option retenue. Si la zone vient s'intercaler entre deux
entrées non touchées plus loin dans le futur, le setup de cette transition-là reste
seulement réservé en temps (obstacle élargi), sans `SetupEntry`. C'est le régime
conservateur d'avant D8, qui ne sous-estime jamais le temps machine ; il ne concerne plus
la jonction elle-même, qui est le cas fréquent.

**Effet de bord sur un test.** `test_sans_stabilite_le_planning_se_compacte` affirmait
`debuts["J1"] < 100`. Dans ce scénario le retard vaut zéro partout et le poids de
stabilité est mis à zéro : **tous** les placements faisables sont également optimaux, et
l'assertion verrouillait donc un choix arbitraire de CP-SAT, pas un comportement du
modèle. Les nouvelles contraintes ont changé ce choix sans rien casser. Le test est
renommé `test_sans_stabilite_la_solution_derive_de_loriginal` et porte désormais sur la
dérive (`!= 100`), ce qui est bien l'intention d'origine.


### D9 — L'orchestrateur public `resolve_incremental` est le seul chemin de la cascade (2026-09-04)

Nouveau module `scheduling/incremental.py`, au même niveau que `validation.py` et
`dispatcher.py` puisqu'il traverse à la fois `components/` et `solvers/`. Il enchaîne les
six composants dans l'ordre de la §2.4 et devient le point d'entrée unique — c'est lui
qu'appellera le worker de la Discussion 3.

`ScheduleStateManager` n'y apparaît pas explicitement : `ImpactAnalyzer` l'invoque
lui-même et publie son résultat sur `ImpactZone.state`, que consomment ensuite le builder
de contextes et le merger. Le faire tourner une seconde fois dans l'orchestrateur
produirait deux découpages distincts du même planning.

**Deux écarts assumés par rapport à la signature esquissée**
(`resolve_incremental(schedule, event, t_now, config) -> Schedule`) :

1. **`instance` est un paramètre obligatoire.** Tous les composants en dépendent — la
   construction de la sous-instance, les durées de setup, la `Cumulative` WR, le recalcul
   des KPI — et rien ne permet de la retrouver depuis un `Schedule` seul. La signature
   réelle est `resolve_incremental(schedule, event, instance, t_now=None, config=None)`.
2. **Le retour est un `IncrementalResolution`, pas un `Schedule` nu.** Le planning fusionné
   est accessible par `.schedule`, mais un `Schedule` seul perdrait le `MergeReport`, dont
   le worker a besoin pour le KPI de communication (« 6 jobs replanifiés sur 180 », §2.4)
   et l'endpoint `GET /resolutions/{id}/diff` de la Discussion 4. L'objet expose des
   raccourcis (`nb_jobs_affected`, `nb_future_jobs`, `fallback_recommended`, `is_clean`).

**`IncrementalConfig` ne redéfinit aucune politique.** Elle regroupe les points de réglage
des trois composants configurables pour que l'appelant n'ait pas à les instancier à la
main. Un champ à `None` signifie « garder le défaut du composant », pas « passer `None` » :
les fractions et les seuils n'accepteraient pas `None`, seules les surcharges absolues le
font. C'est vérifié par
`test_incremental_orchestrator.py::test_sans_config_les_defauts_des_composants_sappliquent`.

**Le garde-fou de repli reste conforme à H5.** Par défaut (`raise_on_fallback=False`) la
cascade *signale* le dépassement de seuil sur `IncrementalResolution.fallback_recommended`
et poursuit — elle ne route rien vers `LNSRecursiveSolver`. `raise_on_fallback=True` donne
un échec franc pour l'appelant qui le préfère. Une zone sans solution CP-SAT lève
`IncrementalResolutionError` plutôt que de renvoyer `None` silencieusement, pour que le
worker puisse marquer la résolution `failed` avec un message exploitable (§3.5).

**Les scénarios passent désormais par l'orchestrateur.** Le helper local
`_replanifie` de `tests/test_incremental_scenarios.py` enchaînait les composants à la main :
il délègue maintenant à `resolve_incremental`, de sorte qu'aucun chemin de code ne soit
testé différemment de ce qui tournera en production. Le seul test qui appelait encore les
composants directement (comparaison de deux poids de stabilité) fait maintenant deux
passages complets de la cascade. `tests/test_incremental_orchestrator.py` (15 tests) couvre
le chaînage lui-même, dont une équivalence explicite entre l'orchestrateur et
l'enchaînement manuel.

Ces scénarios conservent des surcharges **absolues** (`search_horizon=400`,
`max_impacted_jobs=30`) : ils testent la cascade, pas le dimensionnement de la zone, qui
relève de `test_impact_analyzer.py`. Les garder calibrés sur cette instance précise les
rend indépendants d'un futur ajustement des fractions par défaut (D7).


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

### H6 — RÉSOLUE le 2026-09-04 → voir D7 ci-dessous

L'unité de temps a été tranchée par **audit du code frontend**, pas par supposition.
La conclusion (unité abstraite) et ses conséquences sont consignées en D7.

### H7 — RÉSOLUE le 2026-09-04 → voir D8 ci-dessous

L'option retenue par Khalid (modélisation explicite dans `IncrementalOptimizer`) est
implémentée. Le détail, la justification et la limite résiduelle sont en D8.

### Constat — le planning initial de l'instance d'exemple est très dense (2026-09-03)

CP-SAT compacte le planning initial : il n'y reste presque aucun temps mort. L'absorption
du retard implémentée dans `ImpactAnalyzer` n'a donc rien à absorber sur cette instance, et
une panne machine de seulement 10 unités de temps se propage à **75 % des jobs futurs**,
déclenchant le garde-fou de repli.

Ce n'est pas un défaut de la cascade — c'est une propriété du planning de départ, et
précisément le cas que le garde-fou existe pour détecter. Le critère « une perturbation
locale reste locale » est vérifié là où il a un sens, sur un planning comportant du temps
mort (`tests/test_impact_analyzer.py::test_le_temps_mort_absorbe_le_retard`).

Implication produit à garder en tête : sur un atelier réel dont le planning est optimisé au
plus serré, le réordonnancement incrémental sera souvent hors de son domaine de pertinence.
Il faudra soit conserver de la marge dans le planning initial, soit relever le seuil de
repli. À arbitrer avec Khalid.

## Prochaines étapes prévues

Plan global à 5 discussions :

| # | Sujet | État |
|---|---|---|
| 1 | Composants algorithmiques du réordonnancement incrémental | **en cours** |
| 2 | Scénarios de test approfondis + script de validation dédié | à venir |
| 3 | Worker asynchrone (Redis / RQ) | à venir |
| 4 | Endpoints API (`POST /resolutions/{id}/events`, `GET /resolutions/{id}/diff`) + migrations Alembic | à venir |
| 5 | Déploiement | à venir |

Composants livrés dans la Discussion 1 (un commit poussé par composant) :

| # | Composant | Fichier | Tests | État |
|---|---|---|---|---|
| 1 | `PerturbationEvent` | `models/perturbation.py` | 20 | livré |
| 2 | `ScheduleStateManager` | `components/schedule_state_manager.py` | 14 | livré |
| 3 | `ImpactAnalyzer` / `ImpactZone` | `components/impact_analyzer.py` | 18 | livré |
| 4 | `IncrementalContextBuilder` | `components/incremental_context_builder.py` | 11 | livré |
| 5 | `IncrementalOptimizer` | `solvers/incremental_optimizer.py` | 21 | livré |
| 6 | `ScheduleMerger` + `validation.py` | `components/schedule_merger.py`, `validation.py` | 20 | livré |
| 7 | Garde-fou de repli (signalé, non routé) | `components/impact_analyzer.py` | 9 | livré |
| 8 | Scénarios sur l'instance 10 jobs | `tests/test_incremental_scenarios.py` | 8 | livré |
| 9 | Bornes relatives (unité abstraite, cf. D7) | `components/impact_analyzer.py` | +8 | livré |
| 10 | Setups de jonction en variables (cf. D8) | `solvers/incremental_optimizer.py`, `components/schedule_merger.py` | +6 | livré |
| 11 | Orchestrateur public `resolve_incremental` (cf. D9) | `scheduling/incremental.py` | 15 | livré |

Suite complète hors tests API : **170 tests verts** (141 à la fin des 8 premiers commits).
`python -m tests.validate_example` passe toujours (TWT 3012.84), donc aucune régression sur
le solveur initial. Les tests de
`test_instances.py` / `test_auth.py` / `test_resolutions.py` exigent un PostgreSQL local et
échouent en connexion — situation préexistante, sans rapport avec cette session.
