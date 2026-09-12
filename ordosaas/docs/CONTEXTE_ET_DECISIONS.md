# OrdoSaaS — Contexte et décisions du projet

> Fichier vivant. Il est mis à jour **au moment** où une décision ou une hypothèse est
> prise, pas en fin de session. En cas de conflit factuel avec un prompt de session,
> c'est ce fichier qui fait foi sur l'état réel du code.

## ✅ RÉSOLU — Les temps de setup sont désormais payés (H8 / H9 → D12)

> Session dédiée du 2026-09-05/06, insérée en urgence avant la Discussion 3. Le défaut
> décrit ici est **corrigé** ; la section est conservée parce qu'elle documente une
> correction qui change un résultat présenté comme preuve de performance.

**Le défaut.** Les intervalles de setup séquence-dépendants étaient optionnels, gouvernés
par un booléen que **rien ne forçait jamais à 1**. CP-SAT les mettait donc tous à zéro —
c'est gratuit et cela relâche des contraintes — et aucun setup n'était jamais payé. Deux
emplacements, même cause racine : `CPSATSolver` (H8) et `IncrementalOptimizer._add_setups`
(H9).

**Ce que ça changeait, chiffré.** Sur l'instance d'exemple : 352 unités de setup dues sur
les séquences réellement produites, **0 payée**, 18 transitions en violation,
`total_setup_time` rapporté à 0.

| | Avant | Après |
|---|---|---|
| TWT de référence | **3012.84** | **4422.64** (+46,8 %) |
| Temps de setup payé | 0 | 320 |
| Statut du solveur | `optimal` | `feasible` (optimalité non prouvée) |
| Transitions en violation | 18 | 0 |

**Le résultat de référence a été présenté comme preuve de performance avant correction.**
`TWT = 3012.84` figurait dans `expected_output.json` et servait de mesure de performance du
projet. Il a été obtenu par un modèle qui ne payait aucun setup : il n'est donc pas une
mesure valide de l'ordonnancement produit. C'est un fait, consigné ici sans préjuger de ce
qu'il convient d'en faire — la décision (informer, corriger une communication, republier)
appartient à Khalid.

**Le KPI d'amélioration vs ATCS est concerné aussi.** `ATCSSolver`, heuristique gloutonne,
payait bien ses setups (334 unités) là où CP-SAT n'en payait aucun. L'amélioration affichée
de **59,4 %** comparait donc un planning honnête à un planning qui trichait. Elle est à
recalculer.

Le détail complet — cartographie de la portée, technique retenue, coût mesuré — est en D12.

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

## Approche & patterns — pratiques établies du projet

Ces pratiques ne sont pas des règles décrétées : chacune vient d'un défaut réel qui
aurait été manqué sans elle. Elles s'appliquent par défaut aux sessions suivantes.

### Valider contre un cas construit et calculé à la main avant de clore

Avant de conclure une session, construire un scénario **à la main**, en calculer le
déroulé attendu **avant** de l'exécuter, puis comparer. Pas seulement les tests
unitaires, pas seulement les rapports agrégés.

**Pourquoi** : c'est ainsi que les défauts les plus sérieux ont été trouvés, et jamais
par les tests unitaires.

| Session | Défaut trouvé par une validation manuelle |
|---|---|
| **D13** | Faux positif du signal de repli sur l'annulation d'un job de fin d'horizon — la coupe tombait sur l'entrée de départ elle-même, avec un « trou » nul par construction |
| **D12** (H8/H9) | Trois défauts latents révélés au re-baselining : setup d'origine hors du `NoOverlap`, setups non touchés absents de la `Cumulative` WR, setup périmé non effacé |
| **D10** | Place du setup entrant non réservée derrière une entrée non touchée — planning infaisable en atelier mais déclaré valide |

Le scénario ainsi construit se **conserve comme test permanent** plutôt que d'être jeté
après usage (cf. `test_absorption_precedence.py::test_scenario_calcule_a_la_main`).

### Vérifier qu'un test échoue bien SANS le correctif

Un test qui passe avant et après ne prouve rien. Désactiver temporairement le correctif
et confirmer que les tests censés le couvrir échouent effectivement.

**Pourquoi** : en D14, un premier jeu de 8 tests écrit sur `impacted_job_ids` passait
**identiquement** avec et sans l'absorption — la zone étant de granularité *job*, une
absorption interne à un job y est invisible. Les tests ont dû être réécrits autour de
jobs *témoins* pour observer l'effet réel. Sans cette vérification, la session aurait
livré une couverture fictive.

### Ne jamais affirmer qu'une conclusion tient sans l'avoir re-mesurée

Quand un correctif change ce que le système produit, les conclusions qualitatives déjà
établies doivent être **revérifiées**, pas reconduites par analogie.

**Pourquoi** : après la correction H8/H9, la matrice densité × perturbation a changé
structurellement — la cellule « job urgent / dense » s'est **inversée** (78 % → 12 %),
faisant disparaître la démonstration la plus forte du lien densité/repli. Une simple
reconduction l'aurait laissée dans la documentation comme un fait acquis.

### Distinguer ce qu'un correctif change de ce qu'il révèle

Un correctif rend souvent atteignables des défauts latents jusque-là masqués. Les
traiter comme des découvertes distinctes, documentées séparément, et non comme des
régressions du correctif.

### Mesurer avant de choisir entre deux approches

Quand deux approches sont plausibles, mesurer plutôt qu'argumenter — et documenter les
chiffres, pas seulement la conclusion.

**Pourquoi** : en D13, la définition littérale du signal de troncature aurait déclenché
le repli sur 8 cellules sur 9. C'est la mesure, et non le raisonnement, qui a imposé de
distinguer les trois points de coupe.

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


### D10 — Garde aval sur les obstacles : correction d'un défaut réel trouvé par le livrable 1 de la Discussion 2 (2026-09-04)

**Ce n'est pas une clarification de limite connue, c'est un bug.** Le livrable 1 devait
construire un scénario provoquant la limite résiduelle de D8 (zone intercalée entre deux
entrées non touchées). Ce scénario a confirmé que cette limite-là est bénigne (voir
« Constat A » ci-dessous), mais il a révélé au passage un **défaut distinct et non
documenté**, dans l'autre sens de transition.

**Le défaut.** Rien ne réservait la place du setup **entrant** d'une opération de la zone
placée juste derrière une entrée non touchée. Les obstacles étaient élargis vers l'amont
(sens `zone → non touchée`) mais jamais vers l'aval (sens `non touchée → zone`). Le
solveur pouvait donc plaquer une opération de la zone contre la fin d'une entrée non
touchée, avec un écart nul, alors que la transition exige un temps de setup.

Reproduction déterministe, avant correction (`stability_weight = 0`, deadline serrée sur
J3 pour que le solveur veuille l'avancer au maximum) :

```
J1 op [100-150]   setup: AUCUN
J3 op [150-210]   setup: AUCUN        <- collée à J1, écart = 0
setup J1->J3 requis physiquement = 40 -> il manque 40 unités
violations validate_schedule : []     -> le planning passe pourtant la validation
```

**Gravité.** Le planning fusionné est **infaisable en atelier tout en étant déclaré
valide**. Il échappe au validateur canonique parce que `scheduling/validation.py` ne
vérifie que chevauchement, précédence et Cumulative WR — jamais qu'un `SetupEntry`
corresponde au prédécesseur réel de l'opération, ni que la place d'un setup manquant
existe.

**Portée.** Le défaut vaut pour **toute** entrée non touchée suivie d'une opération de la
zone : reproduit sur une entrée de jonction *et* sur une entrée non touchée ordinaire.

**Ce n'est pas une régression de D8.** Avant D8 l'obstacle de la première entrée non
touchée était élargi vers l'amont ; l'aval n'a jamais été modélisé, ni avant ni après. D8
n'a donc ni créé ni couvert ce défaut — il était antérieur et simplement jamais atteint
par les scénarios existants, qui ne poussaient pas le solveur à coller une opération.

**Le correctif (option retenue par Khalid) : réservation conservatrice en aval.** Dans
`_build_untouched_obstacles`, l'obstacle de chaque entrée non touchée est désormais élargi
vers l'aval de `garde_aval`, le plus long setup sortant vers un job de la zone :

```python
garde_aval = max(
    (sub_instance.get_setup(entry.job_id, job.id, machine_id)
     for job in sub_instance.jobs),
    default=0,
)
fin = max(entry.end_time + garde_aval, debut)
```

C'est la correction d'un défaut **dans l'implémentation de la réservation conservatrice
déjà décidée en D8**, pas une extension de H7/D8. La modélisation explicite en variables
(symétrique de D8) a été écartée : elle annulerait ce choix architectural sans rapport avec
le bug constaté, et dépasse le périmètre d'une session de test et validation.

**Les DEUX sens sont désormais couverts par une garde de même nature** — une réservation
conservatrice bornée par le plus long setup possible, sans émission de `SetupEntry` :

```
[zone] --garde amont--> [non touchée] --garde aval--> [zone]
```

| Sens de transition | Garde | Statut |
|---|---|---|
| `zone → non touchée` (amont) | `garde` = plus long setup entrant depuis un job de la zone | préexistante, **confirmée en place** |
| `non touchée → zone` (aval) | `garde_aval` = plus long setup sortant vers un job de la zone | **ajoutée par D10** |

La garde amont s'applique aux entrées non touchées au-delà de la première (la première,
la jonction, a son setup modélisé en variables par D8). La garde aval s'applique à
**toutes** les entrées non touchées, jonction comprise, puisque D8 ne traite que le setup
*entrant* de la jonction et laisse son aval libre.

**Tests de non-régression permanents**, dans `tests/test_incremental_jonctions.py` (et non
comme outil de diagnostic jeté après usage) : 4 tests couvrent le Constat B et échouent
effectivement si l'on désactive `garde_aval` — vérifié explicitement. Les scénarios sont
déterministes : c'est la géométrie du planning (J3 ne peut pas passer avant J1, faute de
place entre T_now et le début de J1) qui force le placement recherché, pas un aléa CP-SAT.

### Constat A — la limite résiduelle de D8 est confirmée BÉNIGNE pour la validité (2026-09-04)

Résultat du scénario que le livrable 1 visait initialement. Une zone intercalée entre deux
entrées non touchées ne produit **aucun chevauchement** : la réservation conservatrice fait
son office, et la place du setup réellement en vigueur existe bien dans le planning fusionné.

Ce qui reste faux est une **métadonnée**, pas la validité. Précisément :

| Élément | Fiabilité après fusion |
|---|---|
| **Quelles entrées** | Les entrées non touchées **au-delà de la première de leur machine**. La première (la jonction) est correctement traitée par D8. |
| `SetupEntry.start_time` / `end_time` | **Fiable.** La position temporelle tombe dans une zone réservée, donc sans chevauchement. |
| `SetupEntry.from_job_id` | **Peut être périmé.** Il nomme le prédécesseur d'origine, qui n'est plus forcément celui qui précède l'opération après réordonnancement. |
| `SetupEntry.duration` | **Peut être périmée.** C'est la durée de l'ancienne transition, pas de la nouvelle — elle peut sous-estimer le setup réel. |

Exemple observé : `J2` conserve `setup J1->J2 d=20` alors que `J3` la précède désormais et
que la transition réelle `J3 → J2` vaut 30.

**Conséquence pour la Discussion 4** (endpoint de diff, consommateurs de ces données) : ne
pas se fier au `from_job_id` ni à la `duration` d'un `SetupEntry` porté par une entrée non
touchée au-delà de la première de sa machine — **seule sa position temporelle est fiable**.
Un KPI de temps de setup total calculé naïvement sur ces champs sera légèrement faux.

**Décision de Khalid : ne pas corriger.** Recalculer ces dates rouvrirait exactement le
risque tranché en H7/D8 — ne jamais fabriquer une date de setup hors du modèle CP-SAT —
pour un gain nul, puisqu'aucune invalidité n'en découle. La limite est verrouillée telle
qu'observée par
`test_incremental_jonctions.py::test_la_metadonnee_de_setup_peut_rester_perimee_au_dela_de_la_jonction`,
qui **constate** le comportement au lieu de l'affirmer : le jour où cette limite sera
levée, ce test échouera et signalera qu'il faut mettre à jour D8/D10 — et non contourner
le test.


### Constat — densité du planning × perturbation : les données de la question produit (2026-09-04, **re-mesuré le 2026-09-06**)

Livrable 2 de la Discussion 2. Rapport reproductible : `python -m tests.densite_report`,
qui régénère `docs/densite-perturbation.md`. **Descriptif, il ne tranche pas la question
produit** — il fournit les chiffres pour que Khalid le fasse.

> ⚠️ **Les chiffres ci-dessous sont ceux d'APRÈS la correction de H8/H9 (cf. D12).** La
> première version de cette matrice avait été mesurée en étirant un planning produit par
> l'ancien solveur, qui ne payait aucun setup. Le changement n'est **pas** un simple
> ajustement numérique : la structure du planning sous-jacent a changé, et une conclusion
> de la version d'origine a disparu (voir « Ce qui a changé qualitativement »).

#### Les deux leviers écartés — re-mesurés avec le solveur corrigé

Les mesures qui justifiaient d'écarter les leviers évidents dataient de l'ancien solveur.
Refaites le 2026-09-06 avec le solveur corrigé, elles **confirment** la conclusion :

| Levier | Plage balayée | Utilisation obtenue | Temps mort interne |
|---|---|---|---|
| Desserrer les deadlines | ×1.0 → ×4.0 | 88.3 % → 73.2 % | 45 → 16 (**diminue** à ×2.5 : 3) |
| Raccourcir les durées | ×1.0 → ×0.3 | 88.3 % → 66.4 % | 45 → **0** |

Desserrer les deadlines d'un facteur quatre ne fait descendre l'utilisation qu'à 73 %, loin
des ~36 % visés, et le temps mort interne reste dérisoire. Raccourcir les durées contracte
l'horizon d'autant, et fait même tomber le temps mort à **zéro**, soit l'inverse de l'effet
recherché.

**Dans les huit configurations mesurées, la machine goulot M1 n'a aucun temps mort.** La
correction de H8/H9 renforce ce constat au lieu de l'infirmer, les setups occupant
désormais du temps machine réel.

#### Le levier retenu : l'étirement du planning

Toutes les dates de début (opérations **et** setups) sont multipliées par `s ≥ 1`, les
durées restent inchangées, les deadlines suivent. Trois propriétés le rendent exploitable :
il modélise directement l'un des deux termes de la question produit (« conserver de la
marge »), il conserve les 10 jobs donc évite tout biais de dénominateur, et il préserve la
validité **par construction**. Le levier lui-même n'est pas remis en cause par la
correction de H8 — seules les valeurs mesurées le sont.

#### Les trois variantes, après correction et recalibrage

Les facteurs d'étirement ont été recalibrés le 2026-09-06. `dense` reste **délibérément**
à `s = 1.0` : c'est le planning que CP-SAT produit réellement, et c'est lui que la question
produit met en balance avec l'option « garder de la marge ». Le ramener artificiellement à
69 % pour retrouver le chiffre d'avant correction reviendrait à retirer de la comparaison
le cas qu'elle existe pour éclairer. `modérée` et `détendue` sont recalibrées sur les cibles
d'origine (~51 % et ~36 %), ce qui les rend **directement comparables à densité égale** avec
la première version.

| Densité | `s` | Horizon | Utilisation | Temps mort interne | Par machine | TWT | Jobs en retard |
|---|---|---|---|---|---|---|---|
| dense | 1.0 | 673 | 88.3 % | **45** | M1:**0** M2:43 M3:2 | 4422.64 | 8/10 |
| modérée | 1.7 | 1134 | 52.4 % | 1215 | M1:362 M2:473 M3:380 | 6520.71 | 8/10 |
| détendue | 2.5 | 1662 | 35.7 % | 2552 | M1:775 M2:965 M3:812 | 8908.76 | 8/10 |

La plage couverte (88 → 36 %, soit 53 points) est plus large que celle d'origine (69 → 36 %,
soit 32 points). La progression n'est pas régulière — 36 points entre dense et modérée,
17 entre modérée et détendue — conséquence assumée de garder `dense` sur le planning réel.

**Un artefact de mesure a été corrigé au passage.** La première version de l'étirement
multipliait la date de début du setup par `s` indépendamment de son opération, ce qui
détachait progressivement l'un de l'autre et creusait un écart vide croissant — **862 unités
fictives à `s = 3.0`** — comptabilisé comme de l'occupation machine. L'utilisation plafonnait
ainsi à 43 % au lieu des ~30 % réels. Le setup suit désormais son opération, l'écart
d'origine étant préservé et toute la marge ajoutée placée **avant** le setup. Cet artefact
était invisible avant la correction de H8/H9, puisque aucun planning ne portait alors de setup.

#### Cascade naturelle — la matrice recalibrée

Bornes relâchées, perturbations en valeur absolue identiques d'une variante à l'autre.

| Perturbation | dense (88.3 %) | modérée (52.4 %) | détendue (35.7 %) |
|---|---|---|---|
| Panne machine (M1, 20 u.) | 5/7 — **71 %** → repli | 2/7 — 29 % | 1/7 — **14 %** |
| Job urgent (2 op.) | 1/8 — **12 %** | 3/8 — **38 %** | 2/8 — 25 % |
| Dépassement de durée (×1.5) | 7/7 — **100 %** → repli | 2/7 — 29 % | 1/7 — **14 %** |
| **Moyenne** | **61 %** | **32 %** | **18 %** |

#### Le résultat le plus important : la marge n'aide pas tous les types de perturbation

Le recalibrage sépare nettement deux comportements que la moyenne agrégée confondait :

- **Panne machine et dépassement de durée — la marge fonctionne, et proprement.** Les deux
  lignes sont monotones et l'effet est fort : 71 % → 29 % → 14 % et 100 % → 29 % → 14 %.
  C'est le mécanisme attendu : le temps mort absorbe le retard.
- **Job urgent — la marge n'aide pas, et peut nuire.** La ligne est **non monotone et
  inversée par rapport à l'intuition** : 12 % en dense, **38 % en modérée**, 25 % en
  détendue. Le pire cas n'est pas le planning le plus serré, c'est le planning intermédiaire.

L'explication tient à la nature de la perturbation. Une panne ou un dépassement **subissent**
le planning : le temps mort les absorbe. Une insertion, elle, **exploite** le planning : sur
un planning saturé, le job urgent n'a nulle part où se glisser et se place en fin d'horizon,
où il ne décale rien ; dès qu'il y a de la marge, il s'insère plus tôt et déplace tout ce qui
suit. **La marge, qui protège des aléas subis, ouvre des possibilités d'insertion qui
cascadent.**

Ce résultat n'apparaissait pas dans la version d'origine, où la ligne « job urgent » semblait
au contraire la plus démonstrative (78 % en dense). Il n'est visible qu'après la correction
de H8/H9 et le recalibrage.

#### Comparaison à densité comparable, avant → après correction

Les variantes `modérée` et `détendue` ayant été recalibrées sur les densités d'origine, la
comparaison est à périmètre constant pour elles. Pour `dense`, la densité elle-même a changé
(68.6 % → 88.3 %) : les deux effets s'y mélangent, et la colonne n'est donc pas comparable
terme à terme.

| Perturbation | modérée (50.5 % → 52.4 %) | détendue (36.2 % → 35.7 %) |
|---|---|---|
| Panne machine | 25 % → 29 % | 12 % → 14 % |
| Job urgent | 33 % → **38 %** | 11 % → **25 %** |
| Dépassement de durée | 25 % → 29 % | 12 % → 14 % |

**À densité égale, la cascade est systématiquement plus large après correction.** L'écart est
modeste pour la panne et le dépassement (+4 et +2 points), mais important pour le job urgent
en variante détendue (11 % → 25 %, soit plus du double). Les setups occupant du temps machine
réel, les marges apparentes sont en partie consommées.

#### Régime de production — le piège de lecture, inchangé

Avec les bornes relatives par défaut (D7), le plafond de 0.20 vaut 1 à 2 jobs sur 7-8
futurs : la zone est tronquée dans presque toutes les cellules, à toutes les densités, et
**le garde-fou ne se déclenche jamais**. Ce régime montre que l'incrémental reste borné,
mais il ne dit rien de l'effet de la densité, qu'il masque entièrement.

| Densité | Panne machine | Job urgent | Dépassement durée |
|---|---|---|---|
| dense (88.3 %) | 29 % (tronquée) | 12 % | 29 % (tronquée) |
| modérée (52.4 %) | 14 % (tronquée) | 25 % (tronquée) | 14 % (tronquée) |
| détendue (35.7 %) | 14 % (tronquée) | 25 % (tronquée) | 14 % (tronquée) |

Modérée et détendue y sont **indiscernables** : le plafond relatif les ramène aux mêmes
valeurs. En production, sur cette instance, la densité du planning n'a donc aucun effet
observable sur l'ampleur de la zone.

#### La question produit — ce que ces données disent, et ce qu'elles ne disent pas

La question reste **ouverte et non tranchée** : conserver de la marge à l'optimisation
initiale, ou relever le seuil de repli. Quatre éléments doivent désormais entrer dans
l'arbitrage.

1. **La marge fonctionne pour les aléas subis, pas pour les insertions.** C'est le résultat
   central du recalibrage. Sur une panne ou un dépassement, la marge divise la cascade par
   cinq (71 % → 14 %). Sur un job urgent, elle ne l'améliore pas et peut la tripler
   (12 % → 38 %). Une décision « on garde de la marge » n'a donc pas le même sens selon ce
   que l'atelier subit le plus souvent — c'est une question métier, pas une question
   d'ordonnancement.

2. **L'argument le plus démonstratif de la version d'origine a disparu.** Il reposait sur le
   job urgent en planning dense (78 % → repli). Non seulement il n'existe plus, mais la
   ligne s'est inversée. Ce qui subsiste repose entièrement sur la panne machine et le
   dépassement de durée.

3. **Le coût de la marge a doublé.** Avant correction, passer de dense à détendue coûtait
   +65 % de TWT (3012.84 → 4961.98). Après correction et recalibrage, c'est
   **+101 %** (4422.64 → 8908.76) — pour un bénéfice réel mais limité à deux des trois types
   de perturbation.

4. ~~**Le seuil de repli n'a aucun rôle observable en production.**~~ **RÉSOLU le
   2026-09-11 — voir D13.** Ce constat était exact et pointait un vrai défaut : le plafond
   relatif de D7 (20 %) bornait la zone avant que le seuil de H5 (50 %) puisse l'atteindre,
   si bien que le garde-fou ne se déclenchait jamais en production et que modérée et
   détendue y étaient indiscernables. Le signal de troncature active corrige cela : le
   seuil opère désormais, et de façon discriminante — il se déclenche sur le planning dense
   (cascades réelles de 71 % et 100 %) et sur lui seul. **L'arbitrage entre « marge » et
   « seuil de repli » porte donc maintenant sur deux leviers également actifs**, ce qui
   n'était pas le cas quand la question a été posée.

Ce constat ne tranche aucune de ces questions ; il fournit les données pour le faire.

Tous les plannings fusionnés restent valides dans les 18 cellules de la matrice, régimes et
densités confondus.

### D11 — Le script de validation incrémental a une portée volontairement plus large que le validateur canonique (2026-09-04)

Livrable 3 de la Discussion 2 : `backend/tests/validate_incremental.py`, exécutable
indépendamment de pytest (`python -m tests.validate_incremental`, options `--jonction` et
`--densite`) et utilisable comme bibliothèque via
`valide_resolution(schedule_initial, event, resolution, instance)`.

Chaque contrôle rend son propre **PASS / FAIL / INFO** : le script ne s'arrête pas à la
première erreur et ne renvoie pas un booléen global, afin qu'une seule exécution donne un
diagnostic complet. Il rejoue sans modification les scénarios des livrables 1 et 2 — 22
scénarios, 198 vérifications.

Contrôles : opérations figées intactes, frontières sans chevauchement, validité globale,
cohérence des `SetupEntry` de jonction, place réservée pour les transitions de setup,
absence de dérive hors zone, cohérence du KPI, et respect du contrat de repli.

**Portée plus large que `scheduling/validation.py`, et c'est délibéré.** Le validateur
canonique vérifie chevauchement, précédence et Cumulative WR — jamais la cohérence d'un
`SetupEntry` avec le prédécesseur réel de son opération, ni l'existence de la place d'un
setup manquant. C'est ce trou qui a laissé passer le défaut corrigé en D10 et masqué H8/H9.

Ce trou est comblé **pour l'incrémental uniquement**. Décision de Khalid : ajouter cette
exigence au validateur canonique l'imposerait rétroactivement au solveur LNS initial,
jamais conçu ni testé sous cet angle, ce qui sort du périmètre de la Discussion 2. Ce n'est
donc **pas un oubli à combler plus tard dans `validation.py`**, mais un choix de portée
assumé — à reconsidérer le jour où H8 sera traitée.

**Deux précisions de méthode**, tirées de deux erreurs commises en écrivant le script et
corrigées :

1. L'écart disponible pour un setup se mesure jusqu'au début de l'**opération**, pas
   jusqu'au début d'occupation — mesurer jusqu'à ce dernier inclut le setup dans son propre
   intervalle et le fait toujours apparaître comme nul.
2. La responsabilité d'une transition se juge à l'**entrée réoptimisée**, pas au job. Un
   job peut avoir des opérations figées et d'autres dans la zone ; raisonner par job
   imputait à l'incrémental des transitions entre deux opérations figées qu'il n'avait
   jamais touchées.

**Lecture du contrat de repli.** « Signalé mais jamais routé » (H5, précisé par D9)
signifie qu'aucun basculement automatique vers `LNSRecursiveSolver` n'a lieu — **et non**
qu'aucune modification du planning n'est appliquée. Par conception, `resolve_incremental`
poursuit et applique la réoptimisation même au-delà du seuil, en laissant l'appelant maître
de la décision ; c'est `raise_on_fallback=True` qui donne un échec franc sans planning. Le
script vérifie donc ce qui est réellement contractuel — drapeau exposé et `method_used`
resté à `incremental` — et signale en INFO que le planning a tout de même été appliqué.

Les scénarios du livrable 1 vivent désormais dans `tests/scenarios_jonction.py`, source de
vérité unique consommée à la fois par la suite de tests et par le script, pour qu'ils ne
puissent pas diverger silencieusement.

`tests/test_validate_incremental.py` (15 tests) porte surtout sur la **sensibilité** du
script : chaque contrôle est éprouvé en lui présentant un planning délibérément fauté
(opération figée déplacée, setup de jonction faussé, opération recollée sans place de
setup, dérive hors zone, routage du garde-fou). Un script de validation qui ne détecte rien
ne vaut rien.


### D12 — `AddCircuit` force le paiement des setups (2026-09-06) — résout H8 et H9

#### La technique retenue, et pourquoi les deux autres ont été écartées

Une contrainte **`AddCircuit` par machine**. Les nœuds sont le dépôt et les jobs présents
sur la machine ; un arc `i → j` porte le littéral « j suit immédiatement i ». `AddCircuit`
garantit **structurellement** un prédécesseur et un successeur uniques, donc le littéral de
la paire réellement consécutive vaut nécessairement 1 et son setup est nécessairement payé.
La classe de bug disparaît par construction au lieu d'être colmatée.

Les deux alternatives ont été écartées pour des raisons de **correction**, pas de
préférence :

- **Liaison disjonctive par paire** — imposerait le setup entre *toutes* les paires d'une
  machine, pas seulement les consécutives. Ce n'est exact que si la matrice de setups
  respecte l'**inégalité triangulaire**, ce que rien ne garantit sur des données réelles
  issues d'un CSV. Inacceptable dans une correction dont l'objet même est la validité.
- **Liaison par successeur immédiat explicite** — réintroduirait la famille de risque déjà
  rencontrée en H7/D8, où CP-SAT économisait un setup via un candidat dégénéré.

Un arc est créé pour **chaque** paire ordonnée, y compris à setup nul : sans cela le
circuit ne serait pas hamiltonien et la garantie tomberait. Les intervalles de setup restent
optionnels mais sont gouvernés par le littéral d'arc, si bien que le `NoOverlap` machine et
la `Cumulative` WR continuent de les consommer sans changement.

#### Portée réelle confirmée : bien au-delà de l'instance à 10 jobs

`CPSATSolver.solve_with_context` est le code **partagé**, appelé par quatre chemins :
`CPSATSolver.solve` (résolution directe), `LNSRecursiveSolver` (lignes 125 et 147 — chaque
fenêtre du LNS et ses sous-fenêtres récursives) et `InterWindowOptimizer` (ligne 124). Une
seule correction couvre donc les quatre. Mais cela signifie aussi que **tout résultat déjà
produit par le projet est concerné**, y compris les résolutions LNS sur instances > 50 jobs.

Aucun autre composant ne reconstruit le piège : seuls `cpsat_solver.py` et
`incremental_optimizer.py` importent `cp_model`. `WindowManager` et `ContextPropagator` ne
construisent aucun modèle, `InterWindowOptimizer` délègue, et `ATCSSolver` est une
heuristique séquentielle qui ne peut pas omettre un setup.

#### La borne d'horizon, resserrée — partie intégrante de la correction

L'ancien calcul (`ProblemInstance.horizon`) majorait les setups par la somme de **toutes**
les paires déclarées : 5022 sur l'instance d'exemple, pour un makespan réellement atteint de
673 — des domaines de variables 7,5 fois trop larges. C'était un **artefact du défaut
lui-même** : tant qu'aucun setup n'était payé, la largeur du domaine n'avait aucune
incidence. La borne retenue s'appuie sur le fait qu'une opération n'a qu'**un** setup
entrant, et la majore par le plus long possible : **2020**. Elle est conservée comme partie
de la correction, pas comme un ajout séparé — c'est la première borne correcte une fois la
classe de bug éliminée. Elle est mathématiquement démontrée majorante et vérifiée par test.

#### Le coût en performance, mesuré et assumé

`AddCircuit` ajoute O(n²) booléens par machine et des contraintes de séquencement réelles.
Le problème corrigé — job-shop à setups séquence-dépendants — est **structurellement plus
dur** que celui, faux, que résolvait l'ancien modèle. Mesures sur fenêtres synthétiques
(matrice de setups creuse, budget 30 s) :

| n | Avant | Après |
|---|---|---|
| 10 | 0,08 s — **optimal** | 0,13 s — **optimal** |
| 20 | 0,26 s — **optimal** | 0,67 s — **optimal** |
| 30 | **1,39 s — optimal** | **30,7 s — feasible** |
| 40 | 30,5 s — feasible | 30,8 s — feasible |
| 50 | 30,7 s — feasible | 31,5 s — feasible |

**Aucune régression de faisabilité** : une solution valide est toujours rendue dans le
budget, de 10 à 50 jobs. En revanche la preuve d'optimalité est perdue à partir de n = 30,
là où l'ancien modèle l'obtenait en 1,4 s. Ce n'est pas un ralentissement du même problème,
c'est le prix d'en résoudre un correct.

**Deux leviers identifiés, explicitement renvoyés à une session de performance dédiée :**
`max_jobs_per_window` (défaut 50) et `CPSAT_TIMEOUT` (défaut 30 s). Cette session doit être
située **après la Discussion 3**, car `CPSAT_TIMEOUT` doit s'arbitrer avec le budget de
temps du worker en tête, pas isolément.

#### Reproductibilité de la référence

Avec la configuration de production (4 workers, arrêt à l'horloge), le TWT variait de
4568.71 à 4685.49 selon l'exécution — **2,56 %**, au-delà de la tolérance de 1 % du projet.
Le problème ne convergeant plus dans le budget, aucune valeur figée n'était stable.

`CPSATSolver` accepte désormais `num_search_workers`, `random_seed` et
`max_deterministic_time` en **option**. Aucune signature de méthode publique ne change :
seuls les défauts d'`__init__` sont complétés, et **la configuration de production reste
strictement inchangée** (4 workers, arrêt à l'horloge, aucune graine imposée). Ces
paramètres ne servent **que** la reproductibilité des références et des tests.

Avec `1 worker, seed=42, max_deterministic_time=10`, le résultat est **bit-à-bit
reproductible** : TWT 4422.64, makespan 673, setup 320. Le temps d'horloge varie (73 à
114 s) — c'est le principe d'un arrêt déterministe.

`expected_output.json`, `tests/conftest.py::example_schedule` et
`densite_variants.construit_variantes` utilisent tous cette configuration : sans elle, le
planning de départ changeait à chaque exécution et rendait instables tous les scénarios
bâtis dessus.

#### L'optimalité n'est PAS prouvée, et le fichier le dit

Aucun budget testé ne prouve l'optimalité : `feasible` à 30, 60, 120 et **300 s**. La
valeur 4422.64 est atteinte de façon reproductible à 60 s et à 300 s, avec le même makespan
(673) et le même temps de setup — **indice fort de qualité, qui ne remplace pas une preuve
formelle**. `best_objective_bound = 2130.72` donne la borne inférieure, soit un écart
maximal de **51,8 %** à l'optimum.

`expected_output.json` porte donc `solver_status: "feasible"`, `best_objective_bound`, et la
traçabilité de la correction dans le fichier lui-même
(`previous_total_weighted_tardiness`, `previous_total_setup_time`, `correction_reason`) —
afin que sa correction reste visible pour quiconque le consulte isolément, hors dépôt et
hors `git log`. La méthodologie de test du projet (tolérance symétrique à 1 %) est
inchangée.

#### Trois défauts latents révélés par le re-baselining

Tous inatteignables tant qu'aucun planning ne portait de setup — corriger H8 les a rendus
atteignables, et la re-mesure les a fait apparaître :

1. **Setup d'origine de jonction hors du `NoOverlap`.** L'intervalle optionnel créé par D8
   quand le prédécesseur reste inchangé n'était ajouté à aucun `NoOverlap` : la zone
   pouvait se placer par-dessus.
2. **Setups des entrées non touchées absents de la `Cumulative` WR.** Ils consomment un
   technicien comme les autres ; les omettre autorisait des dépassements de capacité.
3. **Setup périmé non effacé.** Quand le prédécesseur d'une jonction changeait pour une
   transition de durée nulle, aucun `SetupEntry` n'était émis et l'entrée conservait son
   setup d'origine, qui chevauchait alors la zone. `_collect_junction_setups` publie
   désormais `None` dans ce cas, ce que `ScheduleMerger` interprète comme « effacer ».

#### Limite assumée côté incrémental

Le circuit de `_add_setups` ne porte que les jobs de la **zone**. Quand une opération non
touchée s'intercale entre deux opérations de zone sur la même machine, le circuit impose
malgré tout le setup direct zone → zone. C'est une **sur-réservation, jamais une
sous-estimation** : elle ne peut pas produire un planning infaisable en atelier, seulement
une solution un peu moins bonne.

Faire porter le circuit sur tous les occupants de la machine donnerait un modèle exact et
rendrait redondantes les gardes de D8 et D10 — mais entrerait en conflit direct avec les
setups de jonction de D8, deux intervalles actifs sur la même transition rendant le
`NoOverlap` infaisable. Chantier hors périmètre d'une correction de validité.

#### Le canari

`tests/test_setups_payes.py` verrouille la propriété **observable** (l'écart entre deux
opérations consécutives couvre le setup dû), pas la technique employée : les tests
resteraient valides si la modélisation changeait à nouveau. Le canari couvre les **deux**
solveurs — corriger l'un sans surveiller l'autre est exactement ce qui a permis à H9 de
survivre à la vigilance déployée en D8. Un test y fige aussi la limite du validateur
canonique : un planning dont on retire tous les setups sans toucher aux dates lui paraît
parfaitement valide.

### Amélioration de qualité identifiée mais DIFFÉRÉE — setup du contexte gauche sur l'arc du dépôt

Le contexte gauche (dernier job figé d'une machine) est traité par une contrainte
**inconditionnelle** : *tout* job de la machine doit démarrer après `charge + setup(dernier
figé, job)`. C'est sûr mais sur-contraignant, puisqu'un seul job est réellement le premier.

`AddCircuit` permettrait de rattacher ce setup au seul arc `dépôt → premier job`, ce qui
serait à la fois plus correct et moins contraignant, **au bénéfice du LNS comme de
l'incrémental**.

**Volontairement non fait dans cette session**, pour que le nouveau TWT de référence soit
attribuable à un seul changement et ne mélange pas une correction de validité à une
amélioration de qualité distincte et non bloquante — même principe que le traitement du
Constat A en Discussion 2. À traiter dans une session séparée, **après** que la référence
issue de cette session soit stabilisée et validée.


### Cartographie — comment la propagation de cascade s'arrête aujourd'hui (2026-09-11, avant correction)

Établie par lecture du code, préalable à la correction du défaut d'articulation D7 / H5.

#### Le défaut à corriger

Deux garde-fous conçus séparément ne s'articulent pas :

- **D7** borne la recherche : `search_horizon_fraction = 0.15`, `max_impacted_jobs_fraction = 0.20` ;
- **H5** est le seuil de repli : `fallback_threshold = 0.5`.

**20 % < 50 %.** Le plafond de recherche coupe la zone *avant* qu'elle puisse atteindre le
seuil de repli, quelle que soit l'ampleur réelle de la perturbation. Mesuré en Discussion 2 :
des cascades réelles de 71 % et 100 % des jobs futurs, tronquées à 29 % en production, sans
que rien ne le signale. Le résultat reste **valide** — `ScheduleMerger` garantit toujours
l'absence de chevauchement — mais une partie de la cascade n'est jamais réoptimisée, en
silence.

#### Les quatre points de sortie de la boucle

Tous dans `_Propagation` (`components/impact_analyzer.py`) :

| Point de sortie | Emplacement | Nature |
|---|---|---|
| `restant <= 0` après soustraction du temps mort | `push_machine`, l. 467-468 | **Convergence naturelle** — seul cas qui ne lève aucun drapeau |
| `debut > horizon_end` | `push_machine`, l. 462-464 | Troncature contention, `restant` encore > 0 |
| `_occ_start(entry) > horizon_end` | `mark`, l. 437-439 | Troncature précédence (successeur hors horizon) |
| `_at_capacity()` | `mark` l. 444-446, `mark_job` l. 430-432 | Troncature par le plafond de jobs |

**Les deux cas ne sont PAS distinguables aujourd'hui.** Les trois troncatures écrivent dans
le même `zone.truncated`, et la convergence n'écrit rien. On sait donc qu'il y a eu coupe,
jamais laquelle ni si le retard progressait encore. Le signal doit être introduit.

#### Précédence et contention : file commune, logiques distinctes

Elles **partagent la file de travail** — `run()` dépile une entrée et déclenche les deux —
mais leurs logiques de propagation diffèrent :

- **contention** → `push_machine()`, qui **modélise l'absorption** (`restant -= temps_mort`) ;
- **précédence** → `mark()` direct, qui propage `delay` **inchangé**, sans aucune absorption.

Le correctif doit donc intervenir à deux endroits, pas un.

#### Mesure des points de coupe, cellule par cellule

Instrumentation des trois branches sur les 9 cellules de la matrice, en configuration de
production :

| Cellule | Cascade naturelle | Points de coupe observés |
|---|---|---|
| dense / panne | 71 % | capacité ×1, horizon-précédence ×2, **contention active ×3**, contention absorbée ×2 |
| dense / dépassement | 100 % | **capacité ×10**, **contention active ×2**, contention absorbée ×2 |
| dense / job urgent | 12 % | **aucun** |
| modérée × 3, détendue × 3 | 14 à 38 % | horizon-précédence ×1-2 **uniquement** |

**Ce que cette mesure impose au correctif.** Appliquer littéralement « tronqué alors que la
propagation était encore active » ferait déclencher le repli sur **8 cellules sur 9**, la
coupe de précédence se produisant partout. On remplacerait un faux négatif systématique par
un faux positif systématique — c'est-à-dire qu'on reproduirait, à l'envers, le
sur-déclenchement que D7 avait précisément été créé pour corriger.

La discrimination se trouve dans les deux autres branches : le refus par plafond de jobs et
la coupe en contention avec résiduel non absorbable isolent **exactement** dense/panne et
dense/dépassement, et rien d'autre.


### D13 — Le signal de troncature fiabilise le garde-fou de repli (2026-09-11) — résout le défaut D7 / H5

#### Le diagnostic

Deux garde-fous conçus séparément, qui ne s'articulaient pas :

- **D7** borne la recherche : `search_horizon_fraction = 0.15`, `max_impacted_jobs_fraction = 0.20` ;
- **H5** déclenche le repli : `fallback_threshold = 0.5`.

**20 % < 50 %.** Le plafond coupait la zone *avant* qu'elle puisse atteindre le seuil,
quelle que soit l'ampleur réelle de la perturbation. La règle du seuil ne pouvait donc
**structurellement plus se déclencher**. Mesuré en Discussion 2 : des cascades réelles de
71 % et 100 % des jobs futurs, tronquées à 29 % en production, sans que rien ne le signale.
Le résultat restait **valide** — `ScheduleMerger` garantit toujours l'absence de
chevauchement — mais une partie de la cascade n'était jamais réoptimisée, en silence.

#### L'approche retenue : distinguer la coupe de la convergence

`ImpactZone` porte désormais **deux** drapeaux, à ne pas confondre :

- `truncated` — une borne a coupé quelque chose, quelle qu'en soit la raison (conservé
  tel quel, rétrocompatible) ;
- `truncated_before_convergence` — la coupe est intervenue alors qu'un retard résiduel
  progressait encore, sans que rien ne l'ait absorbé.

Seul le second recommande le repli. `fallback_recommended` a donc deux raisons de se
déclencher, la seconde **s'ajoutant** à la première sans la remplacer : la règle du ratio
est conservée pour rester valable si les bornes de D7 changent un jour.

#### Traitement des trois points de coupe, et pourquoi ils diffèrent

| Point de coupe | Traitement | Justification |
|---|---|---|
| **Plafond de jobs** (`mark`, `mark_job`) | Coupe **active** | Le plafond refuse un job que la cascade réclamait : la propagation voulait aller plus loin, par construction |
| **Contention hors horizon** (`push_machine`) | Active **sous conditions** | Voir ci-dessous |
| **Précédence hors horizon** (`mark`) | **Jamais** active | Voir ci-dessous |

**La contention est qualifiée d'active sous deux conditions cumulatives :**

1. l'entrée bloquée appartient à un job **pas encore dans la zone**. Si son job y est déjà,
   toutes ses opérations futures sont de toute façon réoptimisées et la coupe ne fait rien
   perdre ;
2. le trou qui la précède ne suffit pas à absorber le résiduel — test `restant - trou <= 0`.
   Ce trou est connu même au-delà de la borne : s'il absorbe, la cascade aurait convergé là
   et la coupe ne masque rien. Observé 2 fois sur dense/panne et 2 fois sur
   dense/dépassement ; sans ce test, ces coupes compteraient à tort.

**La précédence est exclue, délibérément.** Sa cascade propage le retard **sans jamais
l'absorber** : qu'un successeur lointain tombe hors horizon découle de ce conservatisme,
pas d'une cascade réellement large. Elle est de plus bornée aux opérations restantes d'**un
seul job** (2 à 4 sur l'instance d'exemple), donc ne peut structurellement pas justifier à
elle seule un impact de 50 % des jobs futurs — c'est la contention, déjà dotée d'un modèle
d'absorption, qui porte la croissance à grande échelle. L'exclure ne crée donc pas d'angle
mort sur les cascades larges.

Mesuré : l'inclure aurait fait déclencher le repli sur **8 cellules sur 9**, la coupe de
précédence se produisant partout. On aurait reproduit à l'envers le sur-déclenchement que
D7 avait précisément été créé pour corriger.

Les deux mécanismes partagent donc le même **principe** — troncature = coupe sur
propagation active, pas coupe indistincte — tout en gardant des implémentations distinctes,
comme leur structure l'impose.

#### Un faux positif trouvé en validant, et corrigé

Annuler le job qui finit **en dernier** libère des créneaux de fin d'horizon et ne décale
rien : cascade réelle de 14 %. Le signal se déclenchait pourtant. Cause : la propagation
part de l'opération du job annulé lui-même ; cette entrée étant hors horizon, la coupe
tombait dessus avec un trou nul **par construction**, le curseur partant précisément de là.
La condition 1 ci-dessus traite ce cas, avec test de non-régression.

C'est la validation contre la matrice qui l'a révélé — pas les tests unitaires.

#### Validation contre la matrice de la Discussion 2

Rapport reproductible : `python -m tests.repli_report`, qui génère `docs/repli-signal.md`.

| Densité | Perturbation | Cascade réelle | Zone en production | AVANT D13 | APRÈS D13 |
|---|---|---|---|---|---|
| dense | Panne machine | **71 %** | 29 % | non | **oui** |
| dense | Job urgent | 12 % | 12 % | non | non |
| dense | Dépassement durée | **100 %** | 29 % | non | **oui** |
| modérée | Panne machine | 29 % | 14 % | non | non |
| modérée | Job urgent | 38 % | 25 % | non | non |
| modérée | Dépassement durée | 29 % | 14 % | non | non |
| détendue | Panne machine | 14 % | 14 % | non | non |
| détendue | Job urgent | 25 % | 25 % | non | non |
| détendue | Dépassement durée | 14 % | 14 % | non | non |

**Avant D13 : 0 cellule sur 9. Après D13 : 2 sur 9** — exactement les deux dont la cascade
réelle dépasse le seuil de repli, et aucune autre. **Zéro faux positif, zéro faux négatif.**

Noter que `truncated` est vrai sur **8 cellules sur 9** : c'est bien la distinction entre
troncature et troncature *active* qui fait tout le travail, pas le simple fait d'avoir été
coupé.

#### La question produit de la Discussion 2 est résolue

Le constat de fin de Discussion 2 — « le seuil de repli n'a aucun rôle observable en
production, modérée et détendue y sont même indiscernables, arbitrer entre marge et seuil
suppose que le seuil opère, ce que les mesures ne montrent pas » — **n'est plus valable**.

Le seuil opère désormais, et de façon discriminante : il distingue le planning dense, où la
cascade déborde réellement, des plannings aérés où elle est contenue. L'arbitrage entre
« conserver de la marge à l'optimisation initiale » et « relever le seuil de repli » porte
donc maintenant sur deux leviers **également actifs**, ce qui n'était pas le cas quand la
question a été posée.

Les trois autres éléments de cet arbitrage restent inchangés et ouverts : la marge
fonctionne sur les aléas subis mais pas sur les insertions, son coût a doublé (+101 % de
TWT entre dense et détendue), et l'argument le plus démonstratif de la version d'origine a
disparu au re-baselining. La décision appartient toujours à Khalid.

#### Ce que cette session ne fait pas

- Les bornes de D7 (0.15 / 0.20) sont **inchangées** : ce correctif est orthogonal.
- Le **routage automatique** vers `LNSRecursiveSolver` reste non implémenté (H5) : le repli
  est signalé, jamais appliqué.


### Cartographie — absorption sur la cascade de précédence (2026-09-11, avant correction)

Établie par lecture du code, préalable à D14.

#### Le principe d'absorption de la contention, à transposer

Dans `push_machine()`, un curseur suit la fin de l'occupant précédent de la machine.
Pour chaque entrée suivante : `trou = max(0, debut - curseur)`, puis `restant -= trou`,
et si `restant <= 0` la propagation s'arrête — le planning a absorbé la perturbation. Le
retard décroît **cumulativement** en descendant la machine.

#### La donnée existe-t-elle pour la précédence ?

Oui. Le temps mort interne d'un job est `suivant.start_time - entry.end_time`, calculable
sur les entrées du planning d'origine.

**Règle de séparation à appliquer par défaut** : le trou de précédence se mesure sur les
bornes d'**opération pures** (`start_time` / `end_time`), **jamais** sur l'occupation
incluant le setup (`_occ_start`). Deux raisons :

1. c'est l'analogue exact de la contrainte réellement posée dans le modèle
   (`_add_precedences` : `s2 >= e1`) — c'est le début de l'*opération* qui est contraint
   par la fin de la précédente ;
2. le setup relève de la **contention machine**, pas de la chaîne du job. Mélanger les
   deux ferait qu'un job doté d'un gros setup entrant — dû à un tiers sur sa machine —
   verrait sa propre précédence faussement moins absorbante, pour une raison sans rapport
   avec sa séquence d'opérations.

Cette séparation vaut comme principe pour tout mécanisme de cascade ajouté ultérieurement.

#### Les deux cascades partagent-elles une structure ?

**Non.** La contention vit dans `push_machine()`, qui parcourt séquentiellement avec
absorption. La précédence tient en trois lignes de `run()` qui marquent **toutes** les
opérations en aval d'un coup, avec le **même** retard non réduit. Deux défauts distincts,
pas un : absence d'absorption **et** absence de parcours séquentiel.

#### Pourquoi la précédence ne pourra JAMAIS contribuer au signal de troncature

Cette session devait, dans un second temps, inclure la précédence dans
`truncated_before_convergence` une fois qu'elle serait capable de converger. **Le code
invalide cette prémisse, et pour une raison indépendante de l'absorption.**

Il s'agit d'une **incompatibilité de granularité** entre le plafond et le mécanisme :
`max_impacted_jobs_fraction` opère à la granularité du **job**, tandis que la cascade de
précédence reste entièrement **à l'intérieur des opérations d'un job déjà marqué**, que la
zone retient en totalité. D'où :

- **le plafond de jobs ne peut jamais couper la précédence** — la garde est
  `if entry.job_id not in self.zone.reason_by_job`, et le job y est toujours ;
- **une coupe d'horizon ne fait rien perdre** — `analyze()` compose la zone avec
  `[e for e in state.future_entries if e.job_id in zone.reason_by_job]`, donc *toutes* les
  opérations du job, horizon ou pas.

Vérifié sur un job dont deux opérations sur trois sont largement hors horizon :

```
horizon_end = 250
truncated = True
   pos 1 sur M1 [100-150]
   pos 2 sur M2 [600-650]   <-- au-dela de l'horizon
   pos 3 sur M3 [1100-1150] <-- au-dela de l'horizon
la zone les contient : 3 / 3
```

La cascade de contention en aval n'est pas perdue non plus : les entrées suivant `pos 2`
sur M2 commencent après 650, donc déjà au-delà de l'horizon de 250. **Une coupe de
précédence n'exclut rien que l'horizon n'excluait déjà**, quelle que soit sa position.

**Conséquence : l'exclusion décidée en D13 devient définitive**, et pour cette raison
structurelle — et non plus provisoire en attendant l'absorption. L'inclure signalerait des
coupes où rien n'est perdu, soit exactement le faux positif que D13 a été conçu pour
éliminer.

L'absorption reste néanmoins une amélioration valide **en elle-même** : elle rend la taille
des cascades de précédence plus juste, ce qui profite directement à la qualité de
l'`ImpactZone` et aux mesures de la matrice.


### D14 — La cascade de précédence absorbe le temps mort du job (2026-09-11)

#### La formule retenue

Transposition du principe déjà appliqué à la contention. On descend la chaîne du job en
soustrayant le temps mort rencontré, et on s'arrête dès que le retard est épuisé :

```python
restant, curseur = delay, entry.end_time
for suivant in by_job[entry.job_id]:            # trié par position_in_job
    if suivant.position_in_job <= entry.position_in_job:
        continue
    restant -= max(0, suivant.start_time - curseur)   # temps mort du JOB
    if restant <= 0:
        break                                   # convergence naturelle
    self.mark(suivant, REASON_PRECEDENCE, restant)
    curseur = suivant.end_time
```

Cela corrige **deux** défauts d'un coup : l'absence d'absorption, et l'absence de
parcours séquentiel — les trois lignes d'origine marquaient *toutes* les opérations en
aval avec le *même* retard non réduit.

**Le trou se mesure sur les bornes d'OPÉRATION pures** (`suivant.start_time - curseur`),
jamais sur l'occupation incluant le setup. C'est l'analogue exact de la contrainte
réellement posée dans le modèle (`_add_precedences` : `s2 >= e1`), et le setup relève de
la **contention machine**, pas de la chaîne du job. Les mélanger ferait qu'un job doté
d'un gros setup entrant — imposé par un tiers sur sa machine — verrait sa propre
précédence faussement moins absorbante. Cette séparation vaut comme principe par défaut
pour tout mécanisme de cascade ajouté ultérieurement.

#### Revalidation de la matrice — 3 cellules sur 9 changent

Rapport reproductible : `python -m tests.absorption_report`, qui génère
`docs/absorption-precedence.md`.

| Densité | Perturbation | Avant D14 | Après D14 | Écart |
|---|---|---|---|---|
| dense | Panne machine | 71 % | 71 % | — |
| dense | Job urgent | 12 % | 12 % | — |
| dense | Dépassement durée | 100 % | 100 % | — |
| **modérée** | **Panne machine** | **29 %** | **14 %** | **−15 pts** |
| **modérée** | **Job urgent** | **38 %** | **25 %** | **−13 pts** |
| **modérée** | **Dépassement durée** | **29 %** | **14 %** | **−15 pts** |
| détendue | Panne machine | 14 % | 14 % | — |
| détendue | Job urgent | 25 % | 25 % | — |
| détendue | Dépassement durée | 14 % | 14 % | — |

Toutes les variations sont à la **baisse**, ce qui est structurel : arrêter la
propagation plus tôt ne peut jamais élargir une cascade.

**L'effet se concentre sur la densité intermédiaire**, et c'est explicable : le planning
dense n'a quasiment pas de temps mort à absorber, tandis que le détendu convergeait déjà
avant D14 par la seule contention. La modérée est la seule qui ait du temps mort *et*
dont la précédence sur-propageait faute de le prendre en compte.

#### Les conclusions qualitatives ont été REVÉRIFIÉES

Pas reconduites par analogie :

1. **La marge aide sur les aléas subis** — toujours vrai, et l'écart reste net
   (panne : 71 % → 14 % → 14 % ; dépassement : 100 % → 14 % → 14 %).
2. **La marge n'aide pas sur les insertions** — toujours vrai : le job urgent reste le
   moins coûteux sur le planning saturé (12 % contre 25 %).
3. **Le seuil de repli distingue le planning dense des autres** — toujours vrai, et le
   signal reste exact : 2 cellules sur 9, les mêmes qu'en D13, zéro faux positif.

**Une nuance nouvelle, en revanche** : modérée et détendue donnent désormais des cascades
**identiques**. Une fois qu'un planning comporte assez de marge pour que la cascade
converge d'elle-même, en ajouter davantage ne change plus rien. **L'effet de la densité
n'est donc pas graduel — il y a un seuil**, au-delà duquel la marge supplémentaire est
sans effet sur l'ampleur de la cascade, alors que son coût continue de croître
linéairement. C'est une donnée directement utile à l'arbitrage produit encore ouvert.

#### La précédence est-elle un contributeur réel ou marginal ?

Deux mesures distinctes, sur les 9 cellules en configuration de production :

| Mesure | Occurrence |
|---|---|
| **Absorptions effectives** (la précédence arrête la propagation) | **7 cellules sur 9** |
| Coupes de précédence par l'horizon | 1 cellule sur 9 (dense / panne) |

**Comme mécanisme d'absorption, la précédence est un contributeur fréquent**, pas
marginal : elle intervient dans 7 cellules sur 9. L'amélioration a donc un impact réel,
et pas seulement théorique.

**Comme contributeur au signal de troncature, elle serait redondante** : sa seule coupe
observée se produit dans une cellule que la contention signale déjà. L'exclusion décidée
en D13 et rendue définitive par la cartographie de cette session ne coûte donc rien,
même en pratique.

#### Effet secondaire mesuré : disparition des troncatures parasites

Avant D14, les bornes de D7 marquaient `truncated` sur **8 cellules sur 9**. Après, sur
**2 seulement** — les deux du planning dense, qui déclenchent toutes deux le repli à bon
droit. Les 6 autres étaient des troncatures sans perte réelle, dues à une cascade de
précédence qui ne convergeait jamais. La distinction entre `truncated` et
`truncated_before_convergence` reste utile et testée au niveau unitaire, mais elle n'a
plus d'occurrence sur cette matrice — signe que le bruit a disparu.

#### Un effet non anticipé, trouvé par la validation manuelle

Sur le scénario calculé à la main, la version *sans* absorption ne se contentait pas
d'élargir la zone : elle atteignait 75 % des jobs futurs et **recommandait le repli** —
sur une perturbation pourtant absorbée dès la première transition du job. L'absorption
évite donc aussi des recommandations de repli injustifiées, ce qui n'avait pas été prévu
en ouvrant la session.


### Constat — un planning « optimisé à densité modérée » n'existe pas par simple résolution (2026-09-12)

Vérification préalable à toute tentative de résoudre une instance à ~52 % d'utilisation.
**L'hypothèse redoutée est confirmée**, et plus nettement que ne le laissait penser la
mesure de la Discussion 2.

#### Ce qu'il faudrait atteindre

L'occupation totale est **fixe** : 1708 unités (1388 de durées + 320 de setups payés).
L'utilisation vaut `occupation / (makespan × 3)`, donc viser un taux revient à viser un
makespan :

| Utilisation visée | Makespan nécessaire |
|---|---|
| 88 % (dense actuel) | ~647 |
| 70 % | ~813 |
| **52 % (modérée)** | **~1095** |
| 36 % (détendue) | ~1581 |

#### Ce que CP-SAT rend réellement

Deadlines desserrées jusqu'à ×50, configuration déterministe de la référence dense :

| Deadlines | Makespan | Utilisation | Temps mort | TWT | Statut | Temps |
|---|---|---|---|---|---|---|
| ×1 | 673 | 88.3 % | 45 | 4422.64 | feasible | 107 s |
| ×2 | 742 | 80.3 % | 20 | 519.76 | feasible | 132 s |
| ×4 | 916 | 73.2 % | 16 | **0.00** | **optimal** | 1.3 s |
| ×8 | 709 | **90.6 %** | 1 | 0.00 | optimal | 0.6 s |
| ×16 | 709 | 90.6 % | 1 | 0.00 | optimal | 0.5 s |
| ×50 | 709 | 90.6 % | 1 | 0.00 | optimal | 0.6 s |

#### La démonstration est dans la NON-monotonie

L'utilisation ne décroît pas quand on desserre : elle descend à 73 % (×4) puis
**remonte à 90.6 %** (×8) et y reste, identique, jusqu'à ×50. Desserrer cinquante fois
les deadlines ne produit pas un planning plus aéré qu'à ×8.

La raison est structurelle : **dès que le TWT atteint 0, CP-SAT devient indifférent.**
Tous les plannings faisables sont alors également optimaux, et il rend le premier
trouvé — compact, parce que rien ne l'incite à étaler. Le 73.2 % obtenu à ×4 est un
**accident de recherche**, pas un effet du levier.

L'objectif du modèle le confirme, il ne contient rien d'autre que le retard :

```python
objective_terms = [int(job.weight * 100) * tardiness_vars[job.id] for job in jobs]
model.Minimize(sum(objective_terms))
```

Aucun terme de makespan, aucun terme récompensant la marge. **Et M1, la machine goulot,
a zéro temps mort dans les six configurations mesurées.**

#### Conclusion

Minimiser le retard pondéré et conserver de la marge sont **deux objectifs en tension,
pas un seul**. Un planning qui garde délibérément de la marge ne peut donc pas émerger
d'une simple résolution : il faudrait un mécanisme explicite dans le modèle — contrainte
de temps mort minimal, ou terme d'objectif récompensant la marge conservée, sur le même
principe que `STABILITY_WEIGHT` pour l'incrémental.

C'est une **question de conception**, pas un second appel au solveur. Elle est soumise à
Khalid avant tout choix de mécanisme.

#### Ce que cela dit du « +101 % de TWT » déjà publié

Ce chiffre compare le planning dense (4422.64, résolution réelle) à la variante détendue
(8908.76, **obtenue par étirement**). Il mesure donc en grande partie le coût de **ne pas
ré-optimiser** — une séquence pensée pour un planning serré, subie à une échelle
distendue — et non le coût intrinsèque de la marge. Tant qu'aucun mécanisme de marge
explicite n'existe, **on ne dispose d'aucune mesure du coût intrinsèque de la marge**.


### Cartographie de la couche BDD réelle (2026-09-12) — clôt l'essentiel de H4

Établie par lecture du code, préalable à la persistance des événements et au secteur.
C'est la vérification que H4 réclamait depuis la Discussion 1.

#### 1. Migrations : Alembic est en place, et ce n'est PAS la première

`alembic.ini` présent, et **trois migrations existent déjà** :

| Migration | Objet |
|---|---|
| `0001_initial_schema.py` | Schéma initial |
| `0002_audit_logs.py` | Table `audit_logs` |
| `0003_fix_method_used_constraint.py` | Correction de contrainte sur `resolutions` |

Toute nouvelle migration s'inscrit donc dans une chaîne existante, elle ne l'inaugure pas.

#### 2. `Tenant` — existe, sans secteur, mais porte déjà des défauts

Champs réels : `name`, `slug`, `default_wr`, `default_timeout`, `default_strategy`,
`max_jobs_per_instance`, `max_machines_per_instance`, `max_instances_stored`, `timezone`,
`is_active` (+ `id`, `created_at`, `updated_at` hérités).

**Aucun champ `sector`.** En revanche le modèle porte **déjà des valeurs par défaut au
niveau tenant** (`default_wr`, `default_timeout`, `default_strategy`), ce qui donne un
point d'ancrage naturel à un socle sectoriel.

Convention du projet, à respecter : les énumérations sont des `String(n)` assortis d'un
`CheckConstraint`, jamais un type ENUM natif ni une table de référence — voir
`default_strategy`, `Resolution.status`, `Resolution.method_used`.

#### 3. `SolverConfig` — il manque le levier que le secteur veut régler

Table **par instance** : `tenant_id` + `instance_id` + `created_by` obligatoires, puis
`wr`, `strategy`, `cpsat_timeout`, `max_jobs_per_window`, `min_jobs_per_window`,
`max_recursion_depth`, `max_iterations`, `epsilon`, `junction_radius`, `k1`, `k2`.

**`stability_weight` n'existe pas.** C'est pourtant le levier que les défauts sectoriels
visent en premier (`IncrementalOptimizer(stability_weight=...)`, défaut 0.1). Sans
colonne, un défaut sectoriel n'a nulle part où atterrir.

**Conséquence structurelle importante** : `SolverConfig` exige un `instance_id`. Une
configuration ne peut donc pas exister au moment où le tenant est créé — il n'y a pas
encore d'instance. « Appliquer les défauts sectoriels à la création du tenant » est donc
**impossible par construction**, pas seulement déconseillé.

#### 4. `Resolution` — trois colonnes de §2.7 absentes

Le modèle réel ne porte **ni** `parent_resolution_id`, **ni** `trigger_type`, **ni**
`nb_jobs_affected`, que le schéma de conception (§2.7 de
`architecture-incremental.md`) prévoyait. Divergence réelle, à combler si l'on veut
relier un événement à la résolution qu'il déclenche.

#### 5. `perturbation_events` — la table n'existe pas du tout

Aucune trace dans `app/models/`. `PerturbationEvent` reste ce que D5 avait décidé : une
**dataclass Python pure** (`scheduling/models/perturbation.py`), jamais persistée.

#### 6. Le cœur scheduling est SANS dépendance base, et doit le rester

`scheduling/incremental.py` n'importe que des modules `scheduling.*` — aucun SQLAlchemy,
aucune session. C'est une propriété délibérée (cf. D9) : `resolve_incremental` est
testable et exécutable sans base. Toute persistance doit donc vivre dans une **couche
de service distincte**, qui appelle l'orchestrateur puis écrit — jamais l'inverse.

#### 7. Tester la persistance est possible sans PostgreSQL

`app/models/_types.py` fournit des types portables (`UUID`, `JSONB`) qui compilent sur
PostgreSQL **et** SQLite, ce dernier étant explicitement documenté comme repli local.
`aiosqlite` est installé. Les tests de persistance peuvent donc relire réellement la
base, sans dépendre du PostgreSQL absent en local — lequel explique les échecs
préexistants de `test_instances.py`, `test_auth.py` et `test_resolutions.py`.

#### Statut de H4

La question posée par H4 — « le `schema_bdd.sql` de référence colle-t-il au SQLAlchemy
réel ? » — a maintenant sa réponse : **non, et les écarts sont identifiés** (points 3, 4
et 5 ci-dessus). H4 cesse d'être une incertitude pour devenir une liste de travaux
précise.


### D15 — Secteur du tenant et instrumentation des causes de replanification (2026-09-12)

Deux pistes indissociables : un **socle de configuration par secteur**, et le **journal
d'événements** qui dira ce que ce socle valait vraiment. Le secteur est un point de
départ ; les logs sont la vérité qui le recalibre.

**Aucun endpoint** n'a été créé : cette session construit la couche donnée, la
Discussion 4 l'exposera. Les contrats d'API ne sont pas devinés à l'avance.

#### Piste A — le secteur

**Structure retenue** : `tenants.sector`, `String(30)` + `CheckConstraint` sur six
valeurs, `NOT NULL`, défaut `autre`. C'est la convention **déjà établie** du projet
(`default_strategy`, `Resolution.status`, `method_used`) — un ENUM natif ou une table de
référence divergeraient sans bénéfice pour une taxonomie fermée.

**Les défauts vivent en base**, table `sector_defaults`, clé primaire = le secteur.
Seul modèle du projet sans `id` UUID, parce que c'est une table de référence à
cardinalité fermée. Les ajuster est un `UPDATE`, pas un déploiement — c'est la condition
posée, et elle est vérifiée par un test qui modifie la table et constate le changement.

**`stability_weight` a dû être ajouté à `solver_configs`.** Il est absent du schéma de
conception parce qu'il est **né après lui**, avec l'architecture incrémentale — signe
supplémentaire que `schema_bdd.sql` est un document à réconcilier en continu, pas une
référence figée. Sans cette colonne, `cablage_auto` et `textile` — les deux secteurs au
signal le plus net — n'auraient eu aucun levier distinctif.

**Le socle PROPOSE, il n'applique jamais.** Deux raisons, dont une **structurelle** :
`SolverConfig` exige un `instance_id`, donc aucune configuration ne peut exister au
moment où le tenant est créé — « appliquer à l'inscription » est impossible par
construction, pas seulement discutable. Et `Tenant` porte déjà `default_wr`,
`default_timeout`, `default_strategy`, qui existent pour être fixés librement par
l'utilisateur ; les écraser imposerait ce qui doit rester une suggestion. La fonction
s'appelle donc `defauts_pour_secteur()` et non `resoudre_config()`, pour que son usage
en Discussion 4 reste sans ambiguïté.

#### Les valeurs de départ sont des HYPOTHÈSES, pas des conclusions

Elles reposent sur des indices **structurels** concernant les secteurs industriels
marocains, **sans aucune donnée quantifiée à l'appui** — c'est reconnu dès le départ,
pas un risque découvert après coup. Chaque ligne porte un champ `rationale` disant sur
quoi elle repose et ce qui ne la valide pas.

| Secteur | Écart au défaut | Hypothèse |
|---|---|---|
| `cablage_auto` | `stability_weight` 0.3 | Flux JIS, insertions urgentes fréquentes |
| `textile` | `stability_weight` 0.3 | Fast-fashion, réordonnancements sur commande |
| `plasturgie` | `wr` 8 | Aléas subis, changements de série longs |
| `sous_traitance_mecanique` | `wr` 6 | Profil intermédiaire, moins marqué |
| `agro_alimentaire` | aucun | Profil mixte sans signal net |
| `autre` | aucun | Défaut, aucune supposition |

**À réviser dès que des données réelles existeront.** C'est précisément ce que la piste B
rend possible.

Deux garde-fous de conception : un secteur hors taxonomie lève `SecteurInconnuError` au
lieu de dégrader silencieusement vers `autre` — masquer un défaut d'appelant le rendrait
indétectable ; et une table vide dégrade vers les défauts actuels du projet, jamais vers
une erreur.

#### Piste B — le journal

`PerturbationEvent` reste la dataclass pure de D5 **et** dispose désormais d'une
contrepartie persistée, `PerturbationEventLog`. Les deux coexistent volontairement.

**Le sens de la dépendance est strict**, et verrouillé par un test qui relit le source :

```
app.perturbation_log  ──appelle──>  scheduling.resolve_incremental
                      ──écrit──>    perturbation_events
```

`scheduling/incremental.py` n'importe ni SQLAlchemy ni `app`, et ne doit jamais le faire
(D9). Si ce test tombe un jour, c'est que le sens s'est inversé.

**`base_resolution_id` et `reported_by` sont NON NULS**, conformément au schéma de
conception. La tension apparente avec un futur connecteur MES n'est pas réelle : un
événement d'origine automatisée sera attribué à un **compte de service** dédié dans
`users`. **La future session MES n'aura donc aucune migration de schéma à faire** — c'est
consigné ici pour qu'elle n'ait pas à redécouvrir la question.

**La fonction d'analyse est la mesure, pas la boucle d'ajustement.**
`repartition_des_causes()` dit ce qui provoque réellement les replanifications d'un
tenant. Recalibrer le socle à partir de ce constat est une décision **distincte et
délibérément non automatisée** : on verra d'abord à quoi ressemblent de vraies données.

Deux choix qui évitent des pièges d'appelant : les cinq types sont **toujours présents**
dans le résultat, à zéro si absents — l'absence d'un type est une information ; et un
tenant sans historique renvoie un constat vide explicite (`sans_historique`), jamais une
erreur ni une division par zéro silencieuse.

#### Validation manuelle — le journal contredit le socle

Scénario calculé à la main avant exécution, conservé comme test permanent. Un tenant
`cablage_auto` — dont le socle parie sur les insertions avec `stability_weight` 0.3 —
dont le journal réel donne :

| Type | Compte | Part |
|---|---|---|
| `machine_breakdown` | 6 | **60 %** |
| `duration_change` | 2 | 20 % |
| `urgent_job` | 1 | **10 %** |
| `job_cancel` | 1 | 10 % |
| `resource_change` | 0 | 0 % |

**L'hypothèse sectorielle est contredite** : 60 % d'aléas subis contre 10 %
d'insertions. C'est exactement la boucle recherchée, et la démonstration que
l'instrumentation sert à quelque chose.

#### Ce que la Discussion 4 n'aura plus à concevoir

La couche donnée est là : schéma, migrations, persistance, fonction d'analyse, tous
testés contre une vraie base. **Il ne restera qu'à l'exposer** —
`POST /resolutions/{id}/events` appellera `resout_et_journalise()`, un endpoint de
statistiques appellera `repartition_des_causes()`, et la création d'une `SolverConfig`
pourra consulter `defauts_pour_secteur()`. Les décisions d'API — quand appeler, avec
quelle possibilité de surcharge — restent entières et lui appartiennent.


## Hypothèses en attente de validation par Khalid

### H8 / H9 — RÉSOLUES le 2026-09-06 → voir D12

Corrigées par `AddCircuit` dans les deux solveurs, lors de la session dédiée tenue avant la
Discussion 3 comme recommandé. Le TWT de référence passe de 3012.84 à 4422.64 (+46,8 %).
Reste ouvert, et qui appartient à Khalid : que faire du fait que l'ancienne valeur ait été
présentée comme preuve de performance.

### H4 — PARTIELLEMENT CLOSE le 2026-09-12 → voir la cartographie et D15

**Ce qui est clos.** La question posée — le `schema_bdd.sql` de référence colle-t-il au
SQLAlchemy réel ? — a sa réponse : **non**, et les écarts ont été identifiés puis
comblés pour les tables concernées :

| Écart | Statut |
|---|---|
| `perturbation_events` inexistante | **Créée** (migration 0005) |
| `resolutions` sans `parent_resolution_id` / `trigger_type` / `nb_jobs_affected` | **Ajoutées** (migration 0005) |
| `solver_configs` sans `stability_weight` | **Ajoutée** (migration 0004) |
| Les 5 types de `PerturbationType` et le CHECK SQL | **Alignés**, verrouillé par un test |

**Ce qui reste ouvert.** Le constat de fond demeure : `schema_bdd.sql` est un document
de **conception**, à réconcilier en continu et non une référence figée.
`stability_weight` en est la démonstration — il est absent du schéma non par oubli, mais
parce qu'il est né après lui, avec l'architecture incrémentale. Les tables non touchées
par cette session (`machines`, `jobs`, `operations`, `setup_times`, `time_windows`,
`schedule_entries`, `solution_comparisons`) n'ont **pas** été confrontées au schéma de
référence : le même type d'écart peut s'y trouver.

### H5 — Le routage du garde-fou de repli reste à faire (2026-09-03, **signal fiabilisé le 2026-09-11**)

> Le *signal* est désormais fiable (cf. D13) : il se déclenche exactement sur les cascades
> dont l'ampleur réelle dépasse le seuil, y compris quand le plafond de D7 les tronque.
> Le **routage** reste, lui, non implémenté — c'est toujours l'objet de cette hypothèse.

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

Suite complète hors tests API : **270 tests verts** (141 à la fin des 8 premiers commits,
170 à la fin de la Discussion 1, 189 après le livrable 2 de la Discussion 2).
`python -m tests.validate_example` passe toujours (TWT 3012.84), donc aucune régression sur
le solveur initial. Les tests de
`test_instances.py` / `test_auth.py` / `test_resolutions.py` exigent un PostgreSQL local et
échouent en connexion — situation préexistante, sans rapport avec cette session.
