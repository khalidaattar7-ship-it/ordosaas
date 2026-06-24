# OrdoSaaS

![CI](https://github.com/khalidaattar7-ship-it/PFA/actions/workflows/ci.yml/badge.svg)

**OrdoSaaS** est une plateforme SaaS multi-tenant d'**ordonnancement de production industrielle**. Elle permet d'importer des instances d'ateliers (machines, jobs, opérations, temps de réglage séquence-dépendants), de les résoudre avec plusieurs solveurs d'optimisation (CP-SAT exact, ATCS heuristique, LNS récursif par fenêtres), de visualiser les plannings sous forme de diagrammes de Gantt interactifs, et de comparer les performances des différentes approches.

> Objectif : minimiser le **retard pondéré total** (Total Weighted Tardiness) sous contraintes de précédence, de non-chevauchement machine, et de ressources renouvelables (techniciens de setup, *WR*).

```
┌──────────┐      ┌───────────┐      ┌────────────┐
│ Frontend │ ───▶ │  Backend  │ ───▶ │ PostgreSQL │
│  (React) │ HTTP │ (FastAPI) │  SQL │            │
└──────────┘      └───────────┘      └────────────┘
                        │
                        ▼
                ┌───────────────┐
                │  scheduling   │  CP-SAT / ATCS / LNS récursif (OR-Tools)
                └───────────────┘
```

*(Capture d'écran du Gantt : `docs/gantt.png` — placeholder)*

## Architecture

| Couche       | Technologie |
|--------------|-------------|
| **Backend**  | FastAPI (Python 3.12), SQLAlchemy 2 async, Alembic, OR-Tools (CP-SAT) |
| **Frontend** | React 18 + Vite, React Router, TanStack Query, Zustand, Recharts, Tailwind CSS |
| **Base de données** | PostgreSQL 16 |
| **Infra**    | Docker / Docker Compose, GitHub Actions CI |

## Installation & lancement

### Prérequis
- Docker & Docker Compose

### Démarrage rapide

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

make build       # construit les images
make up          # lance postgres + backend + frontend
make migrate     # applique les migrations Alembic
make seed        # charge le tenant démo + instance exemple
```

Services exposés :
- **Frontend** : http://localhost:3000
- **Backend API** : http://localhost:8000
- **Swagger** : http://localhost:8000/docs

### Compte de démonstration
Après `make seed` :
- **Email** : `admin@ensias-demo.ma`
- **Mot de passe** : `demo_password`

## Variables d'environnement

### Backend (`backend/.env`)
| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | URL PostgreSQL (asyncpg) |
| `SECRET_KEY` | Clé de signature JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | Durées de validité |
| `ENVIRONMENT` | `development` / `production` / `test` |
| `CORS_ORIGINS` | Origines autorisées (CSV) |

### Frontend (`frontend/.env`)
| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | URL de base de l'API |

## Tests

```bash
make test
# backend complet (pytest + couverture)
docker-compose exec backend pytest tests/ -v --cov=app --cov=scheduling --cov-report=term-missing

# validation de l'instance exemple (compare avec expected_output.json)
docker-compose exec backend python -m tests.validate_example

# benchmarks Avgerinos (ATCS vs CP-SAT)
docker-compose exec backend python -m tests.benchmarks.run_benchmarks
```

## Guide d'utilisation rapide

1. **Importer une instance** — page *Instances* → *Importer*, glissez `jobs.csv`, `operations.csv` (et `setups.csv` optionnel).
2. **Lancer une résolution** — page *Détail d'instance* → *Lancer une résolution*, choisissez la stratégie (`auto`, `cpsat`, `lns`, `atcs`) et les paramètres.
3. **Suivre en temps réel** — la page de résolution affiche la progression des 4 phases (polling 2 s).
4. **Visualiser le Gantt** — barres colorées (retard / à l'heure), setups hachurés, overlay des fenêtres, zoom, panneau de détail au clic.
5. **Comparer** — l'API `/comparisons` calcule les deltas entre deux résolutions.

## Algorithme — LNS récursif en 4 phases

Pour les instances `> SEUIL_EXACT` (50 jobs), le `LNSRecursiveSolver` applique une stratégie hybride inspirée d'Avgerinos et al. (2023) :

1. **Phase 1 — ATCS initial** : solution heuristique rapide (Apparent Tardiness Cost with Setups), qui sert aussi de référence de comparaison.
2. **Phase 2 — Découpage en fenêtres** : `WindowManager` partitionne les jobs en fenêtres temporelles adaptatives (`min/max jobs par fenêtre`).
3. **Phase 3 — Divide & Conquer récursif** : chaque fenêtre est résolue exactement par **CP-SAT**. En cas de timeout, la fenêtre est divisée récursivement (garde-fous `TAILLE_MIN`, `PROFONDEUR_MAX`), avec propagation de contexte : **frontière gauche exacte** (résultat optimisé précédent) / **frontière droite approximative** (ATCS).
4. **Phase 4 — Optimisation inter-fenêtres** : `InterWindowOptimizer` (inspiré *Link State* + *Distance Vector*) identifie les jonctions coûteuses et réoptimise localement des micro-fenêtres autour des frontières.

Pour `≤ SEUIL_EXACT`, le `SolverDispatcher` route directement vers **CP-SAT** (solution prouvée optimale).

### Modèle CP-SAT
- Variables d'intervalle par opération + variables de setup optionnelles séquence-dépendantes
- Contraintes : précédence intra-job, `NoOverlap` par machine (ops + setups), `Cumulative` sur les setups (capacité = `WR` techniciens)
- Objectif : `min Σ wⱼ · Tⱼ` (retard pondéré, ×100 pour rester en entiers)

## Métriques de qualité

| Métrique | Cible | État |
|----------|-------|------|
| Instance exemple (10 jobs / 3 machines) | TWT prouvé optimal | ✅ validé (`validate_example`) |
| Contraintes (précédence, no-overlap, WR) | 0 violation | ✅ vérifié par tests |
| Couverture de tests backend | ≥ 75 % | gardé par la CI (`--cov-fail-under=75`) |
| Écart ATCS vs CP-SAT | reporté par le benchmark | `run_benchmarks.py` |

## Structure du projet

```
ordosaas/
├── backend/
│   ├── app/            # auth, users, machines, instances, resolutions,
│   │                   # comparisons, tenant, audit, models, seed.py
│   ├── scheduling/     # solvers (cpsat, atcs, lns), components, dispatcher
│   ├── alembic/        # migrations
│   └── tests/          # unit + integration + benchmarks + fixtures
├── frontend/           # React (api, components/gantt, pages, hooks, stores)
├── docker-compose.yml / docker-compose.prod.yml
├── Makefile
└── .github/workflows/  # ci.yml, deploy.yml
```

## Déploiement sur Railway (gratuit, sans carte bancaire)

OrdoSaaS se déploie en **un seul service** sur Railway : le backend FastAPI sert
aussi le frontend React buildé (un `Dockerfile` multi-stage à la racine du repo
construit le frontend puis le bundle dans l'image backend).

1. Créer un compte sur [railway.app](https://railway.app) (*Sign up with GitHub*).
2. **New Project → Deploy from GitHub repo** → sélectionner `khalidaattar7-ship-it/PFA`.
3. Railway détecte le **`Dockerfile` à la racine** (build frontend + backend).
4. Ajouter une base : **New → Database → PostgreSQL**. Railway injecte
   automatiquement `DATABASE_URL` (format `postgres://…`, converti en
   `postgresql+asyncpg://` par l'app).
5. Sur le service backend, ajouter les variables d'environnement :
   - `SECRET_KEY` = une chaîne aléatoire de 64 caractères
   - `ENVIRONMENT` = `production`
   - `CORS_ORIGINS` = `*` (ou l'URL publique Railway une fois connue)
6. Déployer. Au premier démarrage, `start.sh` applique les migrations Alembic
   puis le seed, et lance uvicorn sur `$PORT`. Le frontend est servi sur le même
   domaine (les appels `/api/v1/...` sont gérés directement par FastAPI).

Healthcheck : `GET /healthz` → `{"status":"ok"}`.
Identifiants de démo : **admin@ensias-demo.ma** / **demo_password**.

> Le `Dockerfile` et le `railway.json` à la racine pilotent ce déploiement.
> `ordosaas/backend/{Dockerfile,Procfile,railway.json,nixpacks.toml}` permettent
> aussi un déploiement backend-seul. Un `render.yaml` (blueprint Render) est
> également fourni.

## Références

- **Avgerinos, I. et al. (2023)** — *A hybrid CP / heuristic approach for the weighted tardiness scheduling problem with sequence-dependent setups.*
- **Taillard, É. (1993)** — *Benchmarks for basic scheduling problems*, European Journal of Operational Research.
- **Google OR-Tools** — CP-SAT solver, https://developers.google.com/optimization

---

© OrdoSaaS — Projet de Fin d'Année (PFA), ENSIAS.
