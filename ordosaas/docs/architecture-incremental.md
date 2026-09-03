# Architecture technique — Réordonnancement incrémental & worker asynchrone

## 1. Principe directeur

Les deux chantiers sont liés mais distincts :

- **Le réordonnancement incrémental** est un algorithme. Il se développe et se teste entièrement en local, sans infrastructure particulière.
- **Le worker asynchrone** est une infrastructure. Il sert à exécuter n'importe quelle résolution (complète ou incrémentale) sans bloquer l'API.

Ordre de développement recommandé : construire l'algorithme incrémental d'abord (testable en local avec vos CSV d'exemple), le brancher au worker ensuite, déployer l'ensemble une seule fois.

---

## 2. Réordonnancement incrémental

### 2.1 Ce qui change par rapport à la résolution initiale

Votre LNSRecursiveSolver actuel résout un problème *statique* : aucune notion de "temps présent", tout l'horizon est à construire. Le réordonnancement incrémental introduit une nouvelle donnée : **T_now**, l'instant présent. Tout ce qui précède T_now est un fait accompli, pas une variable.

Différence clé avec la phase 3 existante : dans le LNS initial, le contexte droit (futur) est **approximatif** (solution ATCS, pas encore optimisée). Dans le réordonnancement incrémental, vous disposez déjà d'un planning complet et optimisé pour tout l'horizon — la résolution précédente. Le contexte droit devient donc lui aussi **exact**, simplement non retouché. C'est structurellement plus favorable : vous coordonnez deux vérités (passé figé, futur déjà optimisé), pas une vérité et une approximation.

### 2.2 Nouveaux composants

| Composant | Rôle | Entrée / Sortie |
|---|---|---|
| `PerturbationEvent` | Représente un événement déclencheur | type, timestamp, entités affectées, payload |
| `ScheduleStateManager` | Sépare le planning en figé / futur selon T_now | Schedule + T_now → (frozen_entries, future_entries) |
| `ImpactAnalyzer` | Détermine la zone à ré-optimiser | PerturbationEvent + Schedule → ImpactZone |
| `IncrementalContextBuilder` | Construit les deux contextes exacts aux frontières de la zone d'impact | ImpactZone → BoundaryContext gauche + droit |
| `IncrementalOptimizer` | Ré-optimise uniquement la zone d'impact (CP-SAT + terme de stabilité) | ImpactZone + contextes → WindowResult |
| `ScheduleMerger` | Recolle figé + zone réoptimisée + futur non touché | 3 segments → Schedule cohérent |

Ces composants réutilisent directement `ContextPropagator` et `RecursiveOptimizer` — ce n'est pas un nouveau moteur, c'est une nouvelle façon de les invoquer sur une fenêtre unique délimitée par l'événement plutôt que par le découpage temporel de la phase 2.

### 2.3 Types de perturbations à gérer

| Type | Exemple | Impact direct |
|---|---|---|
| Panne machine | M2 indisponible 10h-13h | Opérations prévues sur M2 dans cette fenêtre |
| Job urgent | Nouvelle commande, deadline serrée | Insertion à trouver dans le planning existant |
| Durée réelle différente | Une opération dure plus/moins longtemps que prévu | Toutes les opérations en aval sur la même machine |
| Annulation de job | Commande annulée | Libère des créneaux, peut avancer d'autres jobs |
| Modification de ressource | WR change temporairement (absence technicien) | Contrainte Cumulative resserrée sur la période |

### 2.4 Flux détaillé

1. **Détection** — un événement arrive via `POST /resolutions/{id}/events` (saisie manuelle du planificateur, ou plus tard connecteur MES).
2. **Séparation du planning** — `ScheduleStateManager` fige tout ce qui est terminé ou en cours (`start_time <= T_now`). Une opération commencée ne peut pas être déplacée, même partiellement — c'est une contrainte dure, pas une variable à optimiser.
3. **Analyse d'impact** — `ImpactAnalyzer` identifie :
   - les opérations directement touchées (sur la machine en panne, pendant la fenêtre d'indisponibilité),
   - la cascade par précédence (opérations en aval du même job),
   - la cascade par contention machine (jobs qui devront se décaler pour absorber le retard sur une machine partagée),
   - le tout borné par un horizon de recherche configurable (ex. ne pas remonter au-delà des 4 prochaines heures ou des 30 prochains jobs), pour éviter de rouvrir tout le planning futur pour un incident local.
4. **Construction du contexte** — `IncrementalContextBuilder` fige le contexte gauche (état réel à T_now) et le contexte droit (planning futur non touché, au-delà de la zone d'impact).
5. **Ré-optimisation ciblée** — `IncrementalOptimizer` relance CP-SAT uniquement sur la zone d'impact, timeout court (10-15s, largement suffisant vu la petite taille de la zone).
6. **Fusion** — `ScheduleMerger` recolle les trois segments, vérifie l'absence de chevauchement aux deux frontières (même logique de validation que `InterWindowOptimizer`).
7. **Persistance** — nouvelle ligne dans `resolutions` (voir schéma ci-dessous), avec le nombre de jobs réellement affectés comme KPI de communication ("6 jobs replanifiés sur 180").

### 2.5 Stabilité du planning — éviter la "nervosité"

Un piège classique : même en ne ré-optimisant qu'une petite zone, CP-SAT peut proposer un réarrangement complètement différent de l'original, alors qu'une solution presque aussi bonne mais plus proche du planning initial existe. Un chef d'atelier qui voit son planning bouleversé pour un gain marginal perd confiance dans l'outil — c'est un phénomène documenté sous le nom de *nervosité du planning* (schedule nervousness) dans la littérature de planification.

Solution : ajouter un terme de pénalité de déviation à l'objectif, pondéré par une constante configurable (`STABILITY_WEIGHT`, par défaut faible, ex. 0.1) :

```
Minimiser : Σ wⱼ · Tⱼ (jobs de la zone d'impact)
          + STABILITY_WEIGHT · Σ |début_nouveau(j) − début_original(j)|
```

C'est une contrainte molle, pas dure : elle guide CP-SAT vers la solution la plus proche de l'originale parmi les solutions quasi optimales, sans l'empêcher de bouger un job si c'est vraiment nécessaire. Techniquement, ça s'implémente avec deux variables auxiliaires par job (delta positif/négatif) — standard en CP-SAT pour linéariser une valeur absolue.

### 2.6 Cas de repli

Si `ImpactAnalyzer` détecte que la cascade dépasse un seuil (ex. plus de 50 % des jobs futurs affectés), l'incrémental n'a plus de sens structurel — mieux vaut relancer un LNS complet. C'est un garde-fou simple à ajouter dans `SolverDispatcher` : router vers `IncrementalOptimizer` par défaut, basculer vers `LNSRecursiveSolver` si la zone d'impact dépasse le seuil.

### 2.7 Modifications du schéma BDD

```sql
-- Table resolutions : nouvelles colonnes
ALTER TABLE resolutions ADD COLUMN parent_resolution_id UUID REFERENCES resolutions(id);
ALTER TABLE resolutions ADD COLUMN trigger_type VARCHAR(20) DEFAULT 'manual'
    CHECK (trigger_type IN ('manual', 'incremental', 'scheduled'));
ALTER TABLE resolutions ADD COLUMN nb_jobs_affected INTEGER;

-- Nouvelle table : journal des événements
CREATE TABLE perturbation_events (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    base_resolution_id  UUID NOT NULL REFERENCES resolutions(id),
    triggered_resolution_id UUID REFERENCES resolutions(id),
    event_type          VARCHAR(30) NOT NULL
                        CHECK (event_type IN ('machine_breakdown', 'urgent_job',
                               'duration_change', 'job_cancel', 'resource_change')),
    payload             JSONB NOT NULL,
    reported_by         UUID NOT NULL REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 2.8 Nouveaux endpoints API

| Méthode | Endpoint | Description |
|---|---|---|
| POST | `/resolutions/{id}/events` | Déclare une perturbation, lance un re-solve incrémental (202, async) |
| GET | `/resolutions/{id}/diff` | Compare avec la résolution parente, ne retourne que les entrées modifiées |

---

## 3. Worker asynchrone

### 3.1 Choix technologique

**Recommandation : RQ (Redis Queue) plutôt que Celery**, pour une équipe de deux développeurs.

| Critère | RQ | Celery |
|---|---|---|
| Configuration | Minimale, un décorateur suffit | Plus riche, plus de fichiers de config |
| Courbe d'apprentissage | Faible | Plus élevée |
| Retries / scheduling avancé | Basique mais suffisant ici | Très complet |
| Monitoring | Interface `rq-dashboard` simple | Flower, plus complet mais plus lourd à maintenir |
| Adapté à votre échelle | Oui — quelques résolutions/minute | Sur-dimensionné pour le pilote |

Celery devient pertinent si vous avez un jour besoin de tâches périodiques complexes ou de plusieurs types de files avec des priorités fines. Pas nécessaire pour un premier pilote.

### 3.2 Composants et flux

- **Redis** : sert uniquement de broker (file de tâches). Les résultats ne transitent pas par Redis — ils sont écrits directement en base via SQLAlchemy, ce qui évite une duplication d'état entre deux systèmes.
- **API (producteur)** : sur `POST /instances/{id}/resolve` ou `POST /resolutions/{id}/events`, crée la ligne `resolutions` (statut `pending`), enfile la tâche (`task_id = resolution_id`, ce qui permet une corrélation directe), répond `202` immédiatement.
- **Worker (consommateur)** : conteneur Docker séparé, exécute `rq worker`, appelle `SolverDispatcher.solve(...)` ou `IncrementalOptimizer`. Écrit sa progression directement dans `resolutions.progress_detail` (JSONB) après chaque phase.

### 3.3 Progression et polling

Le frontend interroge `GET /resolutions/{id}` à intervalle régulier (2-3s). Le worker met à jour `progress_pct` et `current_phase` en base après chaque étape significative — pas besoin de WebSocket ni de pub/sub Redis pour un MVP.

### 3.4 Annulation coopérative

CP-SAT ne peut pas être interrompu proprement en plein calcul, sauf en tuant le processus. Deux mécanismes complémentaires :

- **Timeout dur par fenêtre** : `solver.parameters.max_time_in_seconds` garantit qu'aucune fenêtre individuelle ne bloque indéfiniment.
- **Annulation entre fenêtres** : le worker vérifie le statut de la résolution en base entre chaque fenêtre traitée ; si `status = 'cancelled'`, il arrête proprement à la fenêtre suivante.

### 3.5 Gestion des pannes et tâches bloquées

Si le conteneur worker meurt en plein calcul, la résolution reste bloquée en `running` indéfiniment côté base — RQ ne le détecte pas automatiquement. Solution : un job périodique qui marque comme `failed` toute résolution en `running` depuis plus longtemps que son timeout attendu. Toute exception dans le worker doit être capturée : `status = 'failed'`, `error_message` et `error_detail` renseignés, jamais de tâche qui disparaît silencieusement.

### 3.6 Scalabilité

CP-SAT utilise déjà plusieurs threads en interne (`num_search_workers`). Il vaut donc mieux **peu de processus worker** (un par cœur CPU disponible) plutôt que beaucoup de workers légers, pour éviter la sursouscription CPU. `CPSAT_NUM_THREADS` et `WORKER_REPLICAS` doivent être des variables d'environnement, pas des valeurs codées en dur, pour s'adapter à l'hébergement (pilote cloud, cloud marocain dédié, ou on-premise chez le client).

### 3.7 Docker Compose — extrait

```yaml
services:
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  worker:
    build: ./scheduling_service
    command: rq worker --url redis://redis:6379
    depends_on:
      - redis
      - db
    environment:
      DATABASE_URL: ${DATABASE_URL}
    deploy:
      replicas: 2

  api:
    build: ./backend
    environment:
      REDIS_URL: redis://redis:6379
    depends_on:
      - redis
      - db

volumes:
  redis_data:
```

---

## 4. Comment les deux s'articulent

`SolverDispatcher` route désormais sur deux critères au lieu d'un seul :

- **Taille de l'instance** (existant) → `CPSATSolver` ou `LNSRecursiveSolver`
- **Nature de la requête** (nouveau) → si c'est un événement sur une résolution existante → `IncrementalOptimizer`, avec repli vers `LNSRecursiveSolver` si la cascade est trop large (§2.6)

Le worker, lui, ne fait aucune distinction — il reçoit un `task_id`, exécute la fonction associée, écrit le résultat en base.

---

## 5. Ordre d'implémentation suggéré

1. `PerturbationEvent`, `ScheduleStateManager`, `ImpactAnalyzer` — testables en local sur `exemple_jobs.csv` avec des pannes simulées
2. `IncrementalContextBuilder`, `IncrementalOptimizer` (avec terme de stabilité), `ScheduleMerger` — toujours en local, appel direct sans worker
3. Construction de 3-4 scénarios de test synthétiques (panne machine, job urgent, durée dépassée) sur l'instance d'exemple
4. Mise en place Redis + RQ + conteneur worker, branchement de l'incrémental et du LNS existant dessus
5. Endpoints `POST /resolutions/{id}/events` et `GET /resolutions/{id}/diff`
6. Déploiement de l'ensemble
