# OrdoSaaS — Contexte et décisions du projet

> Fichier vivant. Il est mis à jour **au moment** où une décision ou une hypothèse est
> prise, pas en fin de session. En cas de conflit factuel avec un prompt de session,
> c'est ce fichier qui fait foi sur l'état réel du code.

## ⚠️ ALERTE — Les temps de setup ne sont jamais payés (H8 / H9, découvert le 2026-09-04)

> **À lire avant toute nouvelle construction sur ce socle, en particulier avant la
> Discussion 3 (worker).** Ce constat est placé en tête parce qu'il ne relève pas des
> limites bénignes documentées plus bas : il met en cause la validité d'un résultat déjà
> utilisé comme preuve de performance.

Découvert par le script de validation du livrable 3 de la Discussion 2. **Les setups
séquence-dépendants ne sont contraints nulle part** : ni dans le solveur initial, ni dans
l'optimiseur incrémental. Les plannings produits enchaînent des opérations bord à bord
alors que les transitions exigent des setups non nuls.

### Cause racine, commune aux deux

Le patron de modélisation est le même aux deux endroits : un intervalle **optionnel** de
setup est créé par couple `(from_job, to_job, machine)`, gouverné par un booléen `b`, avec
des implications `OnlyEnforceIf(b)` qui placent le setup entre les deux opérations.

**Mais rien ne force jamais `b` à valoir 1 lorsque `from_job` précède réellement `to_job`
sur la machine.** CP-SAT met donc tous les `b` à zéro — c'est gratuit et cela relâche des
contraintes — et aucun setup n'est jamais payé.

| # | Où | Fichier | Portée |
|---|---|---|---|
| **H8** | `CPSATSolver` (solveur initial) | `scheduling/solvers/cpsat_solver.py:87-133` | Tous les plannings initiaux, donc tout le projet |
| **H9** | `IncrementalOptimizer._add_setups` | `scheduling/solvers/incremental_optimizer.py` | Setups internes à la zone réoptimisée |

C'est exactement la classe de défaut contre laquelle D8 avait dû se prémunir pour les
setups de jonction, avec la construction `AddExactlyOne` + prédécesseur immédiat
(`fin_eff` / `dernier` / `AddMaxEquality`). Cette précaution n'a été appliquée qu'aux
jonctions ; les setups ordinaires, eux, sont restés sur le patron défaillant.

### Preuve observée

Séquence de M1 dans le planning initial de l'instance d'exemple, avant toute perturbation :

```
J6  op[0-26]     setup AUCUN
J8  op[26-27]    setup AUCUN   écart=0  requis=0
J1  op[27-109]   setup AUCUN   écart=0  requis=8
J2  op[109-141]  setup AUCUN   écart=0  requis=11
J4  op[141-196]  setup AUCUN   écart=0  requis=19
J7  op[196-250]  setup AUCUN   écart=0  requis=11
J9  op[250-294]  setup AUCUN   écart=0  requis=21
J5  op[294-324]  setup AUCUN   écart=0  requis=5
J10 op[324-422]  setup AUCUN   écart=0  requis=20
J3  op[422-509]  setup AUCUN   écart=0  requis=35
```

Aucun `SetupEntry` n'est émis et aucune place n'est réservée, alors que `get_setup`
renvoie des durées non nulles pour chacune de ces transitions.

### Deux conséquences qui dépassent le périmètre technique

1. **Le résultat de référence est probablement invalide.** `TWT = 3012.84`, figé dans
   `tests/fixtures/expected_output.json` et utilisé comme preuve de performance dans tout
   le projet, a été obtenu **sans jamais payer un seul setup**. Sur M1 seule, les setups
   éludés totalisent 130 unités de temps. Un planning qui les respecterait serait
   nécessairement plus long et plus en retard : le TWT de référence est optimiste, et
   l'écart reste à quantifier.

2. **Cela contredit la formalisation du PFA soutenu.** D'après Khalid, le §2.1 du document
   pose le setup comme une **contrainte obligatoire** entre deux jobs consécutifs sur une
   machine, et non comme une contrainte optionnelle. Le modèle implémenté ne correspond
   donc pas au modèle défendu. *(Le document PFA n'est pas dans le dépôt : ce point est
   rapporté d'après Khalid, il n'a pas été vérifié dans cette session.)*

### Cartographie de la portée réelle (établie le 2026-09-05, avant toute correction)

Vérifiée par lecture du code, pas supposée. Deux questions étaient ouvertes.

#### 1. `CPSATSolver.solve_with_context` est-il partagé avec le LNS ?

**Oui — c'est le même code, appelé par quatre chemins.** La portée de H8 est donc bien
plus large que la seule résolution exacte directe :

| Appelant | Ligne | Ce que ça couvre |
|---|---|---|
| `CPSATSolver.solve()` | `cpsat_solver.py:28` | Résolution exacte directe (≤ 50 jobs) |
| `LNSRecursiveSolver._optimize_window` | `lns_recursive.py:125` | **Chaque fenêtre du LNS** (phase 3) |
| `LNSRecursiveSolver` (récursion) | `lns_recursive.py:147` | Sous-fenêtres récursives |
| `InterWindowOptimizer._optimize_junction` | `inter_window_optimizer.py:124` | Micro-optimisations aux jonctions |

**Conséquence en deux sens.** Bonne nouvelle pour le correctif : corriger H8 en un seul
endroit corrige simultanément la résolution directe, toutes les fenêtres LNS et les
jonctions inter-fenêtres. Mauvaise nouvelle pour l'ampleur du défaut : **tout résultat
déjà produit par ce projet est concerné**, y compris les résolutions LNS sur instances
> 50 jobs, et pas seulement l'instance d'exemple à 10 jobs.

#### 2. Un autre composant construit-il le même piège indépendamment ?

**Non.** Seuls deux fichiers importent `cp_model` : `solvers/cpsat_solver.py` et
`solvers/incremental_optimizer.py`. Les quatre constructions d'intervalle optionnel du
projet s'y répartissent ainsi :

| Emplacement | Rôle | État |
|---|---|---|
| `cpsat_solver.py:90` | Setups du solveur initial | **H8 — défaillant** |
| `incremental_optimizer.py:456` | Setups de jonction (D8) | Correct — forcé par `AddExactlyOne` |
| `incremental_optimizer.py:471` | Setup d'origine de la jonction (D8) | Correct — même `AddExactlyOne` |
| `incremental_optimizer.py:501` | Setups internes à la zone (`_add_setups`) | **H9 — défaillant** |

`WindowManager` et `ContextPropagator` ne construisent aucun modèle. `InterWindowOptimizer`
délègue à `CPSATSolver` et hérite donc du correctif. Il n'y a bien que **deux** points à
corriger.

#### 3. Découverte annexe — `ATCSSolver`, lui, paie les setups

`ATCSSolver` est une heuristique gloutonne, pas un modèle CP-SAT : elle construit la ligne
de temps séquentiellement et ne *peut pas* oublier un setup
(`atcs_solver.py:97-99` : `actual_start = earliest_start + s_dur`).

D'où une asymétrie qui fausse un second KPI, mesurée sur l'instance d'exemple :

| Solveur | TWT | Horizon | Temps de setup payé |
|---|---|---|---|
| ATCS | 7420.88 | 1010 | **334** |
| CP-SAT | 3012.84 | 674 | **0** |

L'« amélioration vs ATCS » affichée, **59,4 %**, compare donc un planning qui paie ses
setups à un planning qui ne les paie pas. Une part indéterminée de cet écart n'est pas une
amélioration d'ordonnancement mais l'effet du défaut. `improvement_vs_atcs_pct` est donc,
lui aussi, à re-baseliner.

#### 4. Ampleur chiffrée sur l'instance d'exemple

Mesurée sur les séquences réellement produites par CP-SAT :

- setups **dus** au titre des transitions effectives : **352 unités** ;
- setups effectivement **payés** (par temps mort fortuit) : **103 unités** ;
- transitions en violation : **18** ;
- `Schedule.total_setup_time` rapporté : **0**.

### Recommandation explicite

**Traiter H8 et H9 dans une session dédiée AVANT la Discussion 3.** Le worker
industrialise l'appel aux solveurs : le brancher maintenant reviendrait à mettre en
production un défaut de fond, et à rendre plus coûteuse encore la reprise du résultat de
référence. La correction touche le cœur du modèle CP-SAT initial et la valeur de référence
du projet — c'est un chantier à part entière, pas un correctif de fin de session.

### Ce qui a été fait dans cette session, et pas fait

- **Fait** : les deux défauts sont identifiés, localisés, prouvés et documentés ici. Le
  script `python -m tests.validate_incremental` les détecte et **sort en échec** sur
  l'instance réelle tant qu'ils ne sont pas corrigés — choix délibéré, pour maintenir la
  pression et éviter qu'ils soient oubliés.
- **Pas fait, volontairement** : aucune correction. Décision de Khalid, cohérente avec le
  périmètre d'une session de test et validation. Le script distingue les transitions
  héritées du planning initial (signalées en INFO, imputables à H8) de celles impliquant
  la zone réoptimisée (en FAIL, imputables à H9).


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


### Constat — densité du planning × perturbation : les données de la question produit (2026-09-04)

Livrable 2 de la Discussion 2. Rapport reproductible : `python -m tests.densite_report`,
qui régénère `docs/densite-perturbation.md`. **Descriptif, il ne tranche pas la question
produit** — il fournit les chiffres pour que Khalid le fasse.

#### Deux leviers de densité mesurés et écartés

Avant de retenir un levier, deux candidats plus évidents ont été mesurés sur l'instance —
et aucun ne fonctionne :

| Levier essayé | Résultat | Pourquoi |
|---|---|---|
| Desserrer les deadlines (×1.5, ×2.5, ×4) | Utilisation **inchangée**, 68-70 % partout | Les deadlines pilotent le retard, pas l'occupation. CP-SAT compacte pareil, avec moins de retard. |
| Raccourcir les durées (×0.7, ×0.5, ×0.3) | Densité stable, remonte même à 80 % à ×0.5 | L'horizon se contracte dans la même proportion. |
| Réduire le nombre de jobs (10 → 4) | Fonctionne (69 % → 39 %) mais **écarté** | Change le dénominateur du ratio « part des jobs futurs » sur lequel porte le garde-fou : les variantes ne seraient plus comparables. |

Dans les deux premiers cas, **M1 reste saturée à 100 %** : la machine goulot porte 509
unités que CP-SAT tasse au plus serré, et aucun réglage de deadline ou de durée ne l'aère.

#### Le levier retenu : l'étirement du planning

Toutes les dates de début (opérations **et** setups) sont multipliées par `s ≥ 1`, les
durées restent inchangées, les deadlines suivent. Trois propriétés le rendent exploitable :
il modélise directement l'un des deux termes de la question produit (« conserver de la
marge »), il conserve les 10 jobs donc évite le biais de dénominateur, et il préserve la
validité **par construction** — la preuve tient en deux lignes et est vérifiée par
`test_densite_variants.py::test_letirement_preserve_la_validite`.

| Densité | `s` | Horizon | Utilisation | Temps mort interne | Par machine | TWT | Jobs en retard |
|---|---|---|---|---|---|---|---|
| dense | 1.0 | 674 | 68.6 % | 240 | M1:**0** M2:70 M3:170 | 3012.84 | 8/10 |
| modérée | 1.4 | 916 | 50.5 % | 792 | M1:169 M2:264 M3:359 | 3764.71 | 7/10 |
| détendue | 2.0 | 1278 | 36.2 % | 1616 | M1:422 M2:553 M3:641 | 4961.98 | 7/10 |

#### Le résultat central — mesuré en deux régimes, ce qui est indispensable

Perturbations en valeur **absolue**, identiques d'une variante à l'autre (une panne de 20
unités reste une panne de 20 unités, quelle que soit la marge que le planificateur s'est
gardée). T_now = un tiers de l'horizon.

**Régime « cascade naturelle »** (bornes relâchées) — c'est lui qui répond à la question,
car il montre jusqu'où la perturbation se propage réellement :

| Perturbation | dense (69 %) | modérée (51 %) | détendue (36 %) |
|---|---|---|---|
| Panne machine (M1, 20 u.) | 4/8 — **50 %** | 2/8 — 25 % | 1/8 — 12 % |
| Job urgent (2 op.) | 7/9 — **78 %** → repli | 3/9 — 33 % | 1/9 — 11 % |
| Dépassement de durée (×1.5) | 6/8 — **75 %** → repli | 2/8 — 25 % | 1/8 — 12 % |

L'effet est net et monotone : la part moyenne des jobs futurs touchés passe de **68 % en
dense à 12 % en détendue**. Le garde-fou de repli ne se déclenche que sur le planning
dense, et jamais sur les deux autres. La marge absorbe donc bien la perturbation, et le
constat de fin de Discussion 1 est confirmé quantitativement.

**Régime « production »** (bornes relatives par défaut de D7) — et c'est un piège de
lecture qu'il faut connaître :

Avec 8 à 9 jobs futurs, le plafond relatif de 0.20 vaut **1 à 2 jobs**. La zone est donc
tronquée par le plafond dans presque toutes les cellules, à toutes les densités, et **le
garde-fou de repli ne se déclenche jamais**. Ce régime montre que l'incrémental reste
borné, mais il ne dit rien de l'effet de la densité, qu'il masque entièrement.

#### Une troisième lecture apparue dans les chiffres

La question produit était posée comme un choix binaire — conserver de la marge à
l'optimisation initiale, ou relever le seuil de repli. Les mesures en font apparaître une
troisième : **sur cette instance, le plafond relatif de D7 borne déjà la zone bien avant
que le seuil de repli n'entre en jeu**, ce qui interroge le rôle réel du garde-fou en
production. Ce point est signalé, pas tranché.

Coût chiffré de l'option « garder de la marge », pour l'arbitrage : le TWT passe de
3012.84 (dense) à 4961.98 (détendue), soit environ +65 %, et l'horizon de 674 à 1278.

Tous les plannings fusionnés sont valides dans les 18 cellules de la matrice, régimes et
densités confondus — y compris sur les zones larges non tronquées.


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


## Hypothèses en attente de validation par Khalid

### H8 / H9 — Les temps de setup ne sont jamais payés → voir l'ALERTE en tête de document

Défauts réels, non corrigés dans cette session par décision de Khalid. **H8** touche
`CPSATSolver` (donc tout le projet, y compris le TWT de référence 3012.84), **H9**
`IncrementalOptimizer._add_setups`. Même cause racine : le booléen des setups optionnels
n'est jamais forcé. À traiter dans une session dédiée **avant la Discussion 3**.

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

Suite complète hors tests API : **204 tests verts** (141 à la fin des 8 premiers commits,
170 à la fin de la Discussion 1, 189 après le livrable 2 de la Discussion 2).
`python -m tests.validate_example` passe toujours (TWT 3012.84), donc aucune régression sur
le solveur initial. Les tests de
`test_instances.py` / `test_auth.py` / `test_resolutions.py` exigent un PostgreSQL local et
échouent en connexion — situation préexistante, sans rapport avec cette session.
