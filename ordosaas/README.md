# OrdoSaaS

**OrdoSaaS** est une plateforme SaaS multi-tenant d'**ordonnancement de production industrielle**. Elle permet d'importer des instances d'ateliers (machines, jobs, opérations, temps de réglage), de les résoudre avec plusieurs solveurs d'optimisation (CP-SAT, ATCS, LNS récursif par fenêtres), de visualiser les plannings sous forme de diagrammes de Gantt, et de comparer les performances des différentes approches.

## Architecture

| Couche       | Technologie |
|--------------|-------------|
| **Backend**  | FastAPI (Python 3.12), SQLAlchemy 2 async, Alembic, OR-Tools (CP-SAT) |
| **Frontend** | React 18 + Vite, React Router, TanStack Query, Zustand, Recharts, Tailwind CSS |
| **Base de données** | PostgreSQL 16 |
| **Infra**    | Docker / Docker Compose |

```
┌──────────┐      ┌───────────┐      ┌────────────┐
│ Frontend │ ───▶ │  Backend  │ ───▶ │ PostgreSQL │
│  (React) │ HTTP │ (FastAPI) │  SQL │            │
└──────────┘      └───────────┘      └────────────┘
                        │
                        ▼
                ┌───────────────┐
                │  scheduling   │  Solveurs CP-SAT / ATCS / LNS
                │   (OR-Tools)  │  + gestion des fenêtres temporelles
                └───────────────┘
```

L'architecture multi-tenant isole les données par `tenant`, avec authentification JWT (access + refresh tokens), gestion des rôles utilisateurs et journalisation d'audit.

## Installation & lancement

### Prérequis
- Docker & Docker Compose

### Démarrage rapide

```bash
# Copier les variables d'environnement
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# Construire et lancer l'ensemble de la stack
make build
make up

# Appliquer les migrations de base de données
make migrate
```

Services exposés :
- **Frontend** : http://localhost:3000
- **Backend API** : http://localhost:8000
- **Documentation API (Swagger)** : http://localhost:8000/docs

## Variables d'environnement

### Backend (`backend/.env`)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | URL de connexion PostgreSQL (asyncpg) |
| `SECRET_KEY` | Clé secrète pour signer les JWT (64 caractères en production) |
| `ALGORITHM` | Algorithme JWT (`HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée de validité de l'access token |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Durée de validité du refresh token |
| `ENVIRONMENT` | `development` ou `production` |
| `CORS_ORIGINS` | Origines autorisées (séparées par des virgules) |

### Frontend (`frontend/.env`)

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | URL de base de l'API backend |

## Tests

```bash
make test
# équivalent à :
docker-compose exec backend pytest -v --cov=app --cov=scheduling --cov-report=term-missing
```

Les tests couvrent l'authentification, les instances, les résolutions, et chaque solveur (CP-SAT, ATCS, LNS), ainsi que la gestion des fenêtres temporelles. Des benchmarks de référence (Avgerinos, Taillard) sont inclus dans `backend/tests/benchmarks/`.

## Structure du projet

```
ordosaas/
├── backend/            # API FastAPI + moteur d'ordonnancement
│   ├── app/            # Domaines : auth, users, machines, instances,
│   │                   #            resolutions, comparisons, tenant, audit
│   ├── scheduling/     # Solveurs (CP-SAT, ATCS, LNS) et composants fenêtres
│   ├── alembic/        # Migrations de base de données
│   └── tests/          # Tests unitaires + benchmarks
├── frontend/           # Application React (Vite)
│   └── src/            # api, components (gantt, layout, common, forms),
│                       # pages, hooks, stores
├── docker-compose.yml      # Stack de développement
├── docker-compose.prod.yml # Stack de production
└── Makefile                # Raccourcis (up, down, test, migrate, lint…)
```

## Commandes Make

| Commande | Action |
|----------|--------|
| `make up` | Démarre la stack en arrière-plan |
| `make down` | Arrête la stack |
| `make logs` | Affiche les logs en continu |
| `make test` | Lance les tests avec couverture |
| `make migrate` | Applique les migrations Alembic |
| `make lint` | Vérifie le code avec Ruff |
| `make seed` | Charge des données de démonstration |
| `make build` | Construit les images Docker |

## Documentation API

Une fois le backend lancé, la documentation interactive Swagger est disponible sur :
**http://localhost:8000/docs**

---

© OrdoSaaS — Projet de Fin d'Année (PFA).
