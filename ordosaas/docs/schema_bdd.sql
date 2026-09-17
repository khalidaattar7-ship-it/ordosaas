-- =============================================================================
-- AVERTISSEMENT AJOUTE AU VERSEMENT DANS LE DEPOT (2026-09-17)
--
-- Ce fichier est un DOCUMENT DE CONCEPTION. Il n'est PAS la source de verite.
-- La source de verite est la suite des migrations Alembic
-- (`backend/alembic/versions/`), qui seule decrit ce que la base contient
-- reellement.
--
-- Il vivait jusqu'ici HORS du depot. C'etait la cause mecanique de la derive
-- decrite par H4 : un document de reference non versionne avec le code ne peut
-- pas etre reconcilie en continu, puisque rien ne signale qu'il a diverge.
--
-- Cette copie est versee VERBATIM, sans aucune autre modification que cet
-- en-tete, afin de preserver un point de reference historique fidele. Les
-- defauts qu'elle contient sont corriges dans le commit SUIVANT, et non ici.
--
-- Ecarts connus au moment du versement (cf. l'audit du 2026-09-17 dans
-- docs/CONTEXTE_ET_DECISIONS.md) : deux CHECK de la forme `IN (..., NULL)` qui
-- ne rejettent rien, des listes de valeurs perimees, l'absence de
-- `solver_configs.stability_weight` et de la table `perturbation_events`.
-- =============================================================================

-- =============================================================================
-- ORDOSAAS — Schéma PostgreSQL complet
-- Système d'Ordonnancement Intelligent SaaS Scalable
-- ENSIAS PFA 2025-2026
-- =============================================================================
-- Conventions :
--   - Toutes les tables ont un tenant_id (multi-tenant via RLS)
--   - UUIDs comme clés primaires (pas d'entiers auto-incrémentés)
--   - Timestamps created_at / updated_at sur toutes les tables
--   - Snake_case pour tous les identifiants
--   - Contraintes CHECK explicites sur les valeurs métier
-- =============================================================================

-- Extensions nécessaires
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. TENANTS (organisations clientes)
-- =============================================================================
-- Un tenant = une usine / organisation qui utilise OrdoSaaS
-- C'est la racine de l'isolation multi-tenant

CREATE TABLE tenants (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                VARCHAR(255) NOT NULL,              -- "Usine Casablanca Nord"
    slug                VARCHAR(100) UNIQUE NOT NULL,       -- "usine-casa-nord" (URL-friendly)
    
    -- Paramètres par défaut du solveur pour ce tenant
    default_wr          INTEGER NOT NULL DEFAULT 5          -- Nb techniciens setup par défaut
                        CHECK (default_wr >= 1 AND default_wr <= 50),
    default_timeout     INTEGER NOT NULL DEFAULT 30         -- Timeout CP-SAT en secondes
                        CHECK (default_timeout >= 5 AND default_timeout <= 300),
    default_strategy    VARCHAR(20) NOT NULL DEFAULT 'auto' -- 'auto','cpsat','lns','atcs'
                        CHECK (default_strategy IN ('auto', 'cpsat', 'lns', 'atcs')),
    
    -- Limites du tenant (pour contrôle usage SaaS)
    max_jobs_per_instance   INTEGER NOT NULL DEFAULT 500,
    max_machines_per_instance INTEGER NOT NULL DEFAULT 20,
    max_instances_stored    INTEGER NOT NULL DEFAULT 100,
    
    -- Métadonnées
    timezone            VARCHAR(50) NOT NULL DEFAULT 'Africa/Casablanca',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- 2. UTILISATEURS
-- =============================================================================

CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Authentification
    email               VARCHAR(255) NOT NULL,
    password_hash       VARCHAR(255),                       -- NULL si invitation en attente
    
    -- Profil
    first_name          VARCHAR(100) NOT NULL DEFAULT '',
    last_name           VARCHAR(100) NOT NULL DEFAULT '',
    
    -- Rôle et statut
    role                VARCHAR(20) NOT NULL DEFAULT 'lecteur'
                        CHECK (role IN ('admin', 'planificateur', 'lecteur')),
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('active', 'inactive', 'pending')),
                        -- pending = invitation envoyée, pas encore acceptée
    
    -- Tokens
    invitation_token    VARCHAR(255),                       -- Token d'invitation par email
    invitation_expires  TIMESTAMPTZ,
    reset_token         VARCHAR(255),                       -- Token reset mot de passe
    reset_expires       TIMESTAMPTZ,
    
    -- Session
    last_login_at       TIMESTAMPTZ,
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (tenant_id, email)                               -- Email unique par tenant
);

-- Index pour les lookups fréquents
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_invitation_token ON users(invitation_token) WHERE invitation_token IS NOT NULL;

-- =============================================================================
-- 3. MACHINES
-- =============================================================================
-- Les machines de l'atelier, configurées par l'Admin du tenant

CREATE TABLE machines (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identification
    external_id         VARCHAR(100) NOT NULL,              -- "M1", "TOUR-01", etc.
    name                VARCHAR(255) NOT NULL,              -- "Tour à commande numérique 1"
    description         TEXT,
    
    -- Statut
    status              VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'maintenance', 'inactive')),
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (tenant_id, external_id)
);

CREATE INDEX idx_machines_tenant_id ON machines(tenant_id);

-- =============================================================================
-- 4. INSTANCES DE PROBLÈME
-- =============================================================================
-- Une instance = un lot de jobs à planifier
-- C'est le point d'entrée de chaque résolution

CREATE TABLE problem_instances (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by          UUID NOT NULL REFERENCES users(id),
    
    -- Identification
    name                VARCHAR(255) NOT NULL,              -- "Lot production semaine 24"
    description         TEXT,
    
    -- Statistiques de l'instance (dénormalisées pour affichage rapide)
    nb_jobs             INTEGER NOT NULL DEFAULT 0,
    nb_machines         INTEGER NOT NULL DEFAULT 0,
    nb_operations       INTEGER NOT NULL DEFAULT 0,
    nb_setups           INTEGER NOT NULL DEFAULT 0,
    
    -- Statut de l'instance
    status              VARCHAR(20) NOT NULL DEFAULT 'draft'
                        CHECK (status IN (
                            'draft',        -- importée, pas encore résolue
                            'solving',      -- résolution en cours
                            'solved',       -- au moins une solution disponible
                            'error'         -- erreur lors de la résolution
                        )),
    
    -- Source des données
    import_source       VARCHAR(20) NOT NULL DEFAULT 'csv'
                        CHECK (import_source IN ('csv', 'manual', 'demo')),
    
    -- Fichiers CSV originaux (stockés en JSON pour traçabilité)
    raw_jobs_csv        TEXT,                               -- Contenu brut du CSV jobs
    raw_operations_csv  TEXT,                               -- Contenu brut du CSV operations
    raw_setups_csv      TEXT,                               -- Contenu brut du CSV setups (optionnel)
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_instances_tenant_id ON problem_instances(tenant_id);
CREATE INDEX idx_instances_created_by ON problem_instances(created_by);
CREATE INDEX idx_instances_status ON problem_instances(status);
CREATE INDEX idx_instances_created_at ON problem_instances(created_at DESC);

-- =============================================================================
-- 5. JOBS
-- =============================================================================

CREATE TABLE jobs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    instance_id         UUID NOT NULL REFERENCES problem_instances(id) ON DELETE CASCADE,
    
    -- Identifiant métier (vient du CSV)
    external_id         VARCHAR(100) NOT NULL,              -- "J1", "CMD-2024-001", etc.
    
    -- Paramètres du problème
    deadline            INTEGER NOT NULL CHECK (deadline > 0),  -- Unité de temps
    weight              NUMERIC(10,4) NOT NULL DEFAULT 1.0      -- Priorité/pénalité retard
                        CHECK (weight > 0),
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (instance_id, external_id)
);

CREATE INDEX idx_jobs_instance_id ON jobs(instance_id);
CREATE INDEX idx_jobs_tenant_id ON jobs(tenant_id);

-- =============================================================================
-- 6. OPÉRATIONS
-- =============================================================================
-- Une opération = une étape d'un job sur une machine spécifique

CREATE TABLE operations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    job_id              UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    machine_id          UUID NOT NULL REFERENCES machines(id),
    
    -- Paramètres de l'opération
    position            INTEGER NOT NULL CHECK (position >= 1), -- Ordre dans la séquence du job
    duration            INTEGER NOT NULL CHECK (duration > 0),  -- Durée de traitement
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (job_id, position),
    UNIQUE (job_id, machine_id)                             -- Un job = une op max par machine
);

CREATE INDEX idx_operations_job_id ON operations(job_id);
CREATE INDEX idx_operations_machine_id ON operations(machine_id);
CREATE INDEX idx_operations_tenant_id ON operations(tenant_id);

-- =============================================================================
-- 7. TEMPS DE SETUP SÉQUENCE-DÉPENDANTS
-- =============================================================================
-- s(i, j, m) = temps de setup sur machine m avant job j si job i précède

CREATE TABLE setup_times (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    instance_id         UUID NOT NULL REFERENCES problem_instances(id) ON DELETE CASCADE,
    
    -- Les trois dimensions de s(i, j, m)
    from_job_id         UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,  -- Job i
    to_job_id           UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,  -- Job j
    machine_id          UUID NOT NULL REFERENCES machines(id),                -- Machine m
    
    -- Durée du setup
    duration            INTEGER NOT NULL DEFAULT 0 CHECK (duration >= 0),
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (instance_id, from_job_id, to_job_id, machine_id)
);

CREATE INDEX idx_setup_times_instance_id ON setup_times(instance_id);
CREATE INDEX idx_setup_times_from_job ON setup_times(from_job_id);
CREATE INDEX idx_setup_times_to_job ON setup_times(to_job_id);
CREATE INDEX idx_setup_times_machine ON setup_times(machine_id);

-- =============================================================================
-- 8. CONFIGURATIONS DE RÉSOLUTION
-- =============================================================================
-- Paramètres choisis par le planificateur avant de lancer le solveur

CREATE TABLE solver_configs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    instance_id         UUID NOT NULL REFERENCES problem_instances(id) ON DELETE CASCADE,
    created_by          UUID NOT NULL REFERENCES users(id),
    
    -- Paramètre principal : ressources renouvelables
    wr                  INTEGER NOT NULL DEFAULT 5          -- Nb techniciens setup simultanés
                        CHECK (wr >= 1 AND wr <= 50),
    
    -- Stratégie de résolution
    strategy            VARCHAR(20) NOT NULL DEFAULT 'auto'
                        CHECK (strategy IN ('auto', 'cpsat', 'lns', 'atcs')),
    
    -- Paramètres LNS
    cpsat_timeout       INTEGER NOT NULL DEFAULT 30         -- Secondes par fenêtre
                        CHECK (cpsat_timeout >= 5 AND cpsat_timeout <= 300),
    max_jobs_per_window INTEGER NOT NULL DEFAULT 50
                        CHECK (max_jobs_per_window >= 5 AND max_jobs_per_window <= 200),
    min_jobs_per_window INTEGER NOT NULL DEFAULT 5
                        CHECK (min_jobs_per_window >= 2 AND min_jobs_per_window <= 20),
    max_recursion_depth INTEGER NOT NULL DEFAULT 4
                        CHECK (max_recursion_depth >= 1 AND max_recursion_depth <= 8),
    max_iterations      INTEGER NOT NULL DEFAULT 5          -- InterWindowOptimizer
                        CHECK (max_iterations >= 1 AND max_iterations <= 20),
    epsilon             NUMERIC(6,4) NOT NULL DEFAULT 0.01  -- Seuil convergence
                        CHECK (epsilon > 0 AND epsilon < 1),
    junction_radius     INTEGER NOT NULL DEFAULT 10         -- Jobs de chaque côté jonction
                        CHECK (junction_radius >= 2 AND junction_radius <= 30),
    
    -- Paramètres ATCS
    k1                  NUMERIC(6,4),                       -- NULL = calibrage automatique
    k2                  NUMERIC(6,4),
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_solver_configs_instance_id ON solver_configs(instance_id);

-- =============================================================================
-- 9. RÉSOLUTIONS (exécutions du solveur)
-- =============================================================================
-- Une résolution = un lancement du solveur sur une instance avec une config

CREATE TABLE resolutions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    instance_id         UUID NOT NULL REFERENCES problem_instances(id) ON DELETE CASCADE,
    config_id           UUID NOT NULL REFERENCES solver_configs(id),
    triggered_by        UUID NOT NULL REFERENCES users(id),
    
    -- Statut de la résolution
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN (
                            'pending',      -- en attente de traitement
                            'running',      -- en cours d'exécution
                            'completed',    -- terminée avec succès
                            'partial',      -- terminée partiellement (certaines fenêtres en erreur)
                            'failed',       -- échec total
                            'cancelled'     -- annulée par l'utilisateur
                        )),
    
    -- Méthode effectivement utilisée (peut différer de la stratégie demandée)
    method_used         VARCHAR(20)                         -- 'cpsat','lns','atcs'
                        CHECK (method_used IN ('cpsat', 'lns', 'atcs', NULL)),
    
    -- Résultats globaux
    total_weighted_tardiness    NUMERIC(15,4),              -- Objectif final
    nb_jobs_late                INTEGER,
    nb_jobs_on_time             INTEGER,
    max_tardiness               NUMERIC(15,4),
    machine_utilization_pct     NUMERIC(6,2),               -- % utilisation moyenne
    total_setup_time            INTEGER,
    
    -- Comparaison avec baseline ATCS
    atcs_weighted_tardiness     NUMERIC(15,4),              -- Valeur ATCS pour comparaison
    improvement_vs_atcs_pct     NUMERIC(6,2),               -- % amélioration vs ATCS
    
    -- Timings
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    duration_seconds    NUMERIC(10,3),                      -- Durée totale en secondes
    
    -- Progression (mis à jour en temps réel pendant la résolution)
    progress_pct        INTEGER DEFAULT 0 CHECK (progress_pct >= 0 AND progress_pct <= 100),
    current_phase       INTEGER DEFAULT 0 CHECK (current_phase >= 0 AND current_phase <= 4),
    progress_detail     JSONB,
    -- Structure de progress_detail :
    -- {
    --   "phase1": {"status": "completed", "duration_s": 0.3},
    --   "phase2": {"status": "completed", "duration_s": 0.1, "nb_windows": 5,
    --              "windows": [{"id":1,"nb_jobs":35},{"id":2,"nb_jobs":42}...]},
    --   "phase3": {"status": "running", "current_window": 3,
    --              "windows": [
    --                {"id":1,"status":"optimal","duration_s":3.2},
    --                {"id":2,"status":"optimal","duration_s":8.5},
    --                {"id":3,"status":"running","progress_pct":40}
    --              ]},
    --   "phase4": {"status": "pending"}
    -- }
    
    -- Message d'erreur si échec
    error_message       TEXT,
    error_detail        JSONB,
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_resolutions_tenant_id ON resolutions(tenant_id);
CREATE INDEX idx_resolutions_instance_id ON resolutions(instance_id);
CREATE INDEX idx_resolutions_status ON resolutions(status);
CREATE INDEX idx_resolutions_created_at ON resolutions(created_at DESC);

-- =============================================================================
-- 10. FENÊTRES TEMPORELLES
-- =============================================================================
-- Les fenêtres créées par le WindowManager pendant la phase 2

CREATE TABLE time_windows (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    resolution_id       UUID NOT NULL REFERENCES resolutions(id) ON DELETE CASCADE,
    
    -- Position et taille
    window_index        INTEGER NOT NULL CHECK (window_index >= 1),  -- F1, F2, F3...
    t_start             INTEGER NOT NULL CHECK (t_start >= 0),
    t_end               INTEGER NOT NULL CHECK (t_end > t_start),
    nb_jobs             INTEGER NOT NULL CHECK (nb_jobs > 0),
    
    -- Résultat de l'optimisation de cette fenêtre
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN (
                            'pending',
                            'running',
                            'optimal',      -- CP-SAT a trouvé la solution optimale
                            'feasible',     -- CP-SAT solution faisable (pas optimale)
                            'atcs_fallback',-- Timeout atteint, solution ATCS conservée
                            'error'
                        )),
    method_used         VARCHAR(20)
                        CHECK (method_used IN ('cpsat', 'atcs', NULL)),
    recursion_depth     INTEGER DEFAULT 0,                  -- Profondeur atteinte lors du D&C
    
    -- KPIs de la fenêtre
    local_weighted_tardiness    NUMERIC(15,4),
    duration_seconds            NUMERIC(10,3),
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_time_windows_resolution_id ON time_windows(resolution_id);

-- =============================================================================
-- 11. PLANNING (résultat de l'ordonnancement)
-- =============================================================================
-- Chaque entrée = une opération placée dans le temps

CREATE TABLE schedule_entries (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    resolution_id       UUID NOT NULL REFERENCES resolutions(id) ON DELETE CASCADE,
    operation_id        UUID NOT NULL REFERENCES operations(id),
    job_id              UUID NOT NULL REFERENCES jobs(id),
    machine_id          UUID NOT NULL REFERENCES machines(id),
    window_id           UUID REFERENCES time_windows(id),
    
    -- Placement dans le temps
    start_time          INTEGER NOT NULL CHECK (start_time >= 0),
    end_time            INTEGER NOT NULL CHECK (end_time > start_time),
    
    -- Setup précédent (NULL si premier job sur la machine)
    setup_from_job_id   UUID REFERENCES jobs(id),
    setup_start_time    INTEGER,                            -- Début du setup
    setup_end_time      INTEGER,                           -- Fin du setup = start_time
    setup_duration      INTEGER DEFAULT 0,
    
    -- Résultat pour ce job
    job_completion_time INTEGER,                            -- NULL si pas la dernière opération du job
    job_tardiness       NUMERIC(15,4),                      -- NULL si pas la dernière opération
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_schedule_entries_resolution_id ON schedule_entries(resolution_id);
CREATE INDEX idx_schedule_entries_job_id ON schedule_entries(job_id);
CREATE INDEX idx_schedule_entries_machine_id ON schedule_entries(machine_id);
CREATE INDEX idx_schedule_entries_tenant_id ON schedule_entries(tenant_id);
-- Index pour le Gantt (requête par machine + résolution)
CREATE INDEX idx_schedule_entries_gantt ON schedule_entries(resolution_id, machine_id, start_time);

-- =============================================================================
-- 12. COMPARAISONS DE SOLUTIONS
-- =============================================================================
-- Quand le planificateur compare deux résolutions

CREATE TABLE solution_comparisons (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by          UUID NOT NULL REFERENCES users(id),
    
    -- Les deux solutions comparées
    resolution_a_id     UUID NOT NULL REFERENCES resolutions(id),
    resolution_b_id     UUID NOT NULL REFERENCES resolutions(id),
    
    -- Delta calculé
    delta_weighted_tardiness    NUMERIC(15,4),              -- B - A (négatif = B meilleure)
    delta_jobs_late             INTEGER,
    delta_machine_utilization   NUMERIC(6,2),
    winner                      VARCHAR(1)                  -- 'A', 'B', ou NULL (ex aequo)
                                CHECK (winner IN ('A', 'B', NULL)),
    
    -- Métadonnées
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_comparisons_tenant_id ON solution_comparisons(tenant_id);

-- =============================================================================
-- 13. LOGS D'AUDIT
-- =============================================================================
-- Traçabilité de toutes les actions importantes (pour l'Admin)

CREATE TABLE audit_logs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id             UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Action
    action              VARCHAR(100) NOT NULL,
    -- Valeurs : 'user.login', 'user.invite', 'user.role_change',
    --           'instance.import', 'instance.delete',
    --           'resolution.start', 'resolution.cancel',
    --           'config.update', 'machine.create', 'machine.update'
    
    -- Contexte
    resource_type       VARCHAR(50),                        -- 'user', 'instance', 'resolution'
    resource_id         UUID,
    
    -- Détail de l'action
    detail              JSONB,                              -- Avant/après pour les modifications
    ip_address          INET,
    user_agent          TEXT,
    
    -- Timestamp
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_tenant_id ON audit_logs(tenant_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- =============================================================================
-- ROW LEVEL SECURITY (RLS) — Isolation multi-tenant
-- =============================================================================
-- Chaque table avec tenant_id est protégée par RLS
-- Le tenant_id courant est passé via une variable de session JWT

-- Activer RLS sur toutes les tables
ALTER TABLE tenants              ENABLE ROW LEVEL SECURITY;
ALTER TABLE users                ENABLE ROW LEVEL SECURITY;
ALTER TABLE machines             ENABLE ROW LEVEL SECURITY;
ALTER TABLE problem_instances    ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations           ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup_times          ENABLE ROW LEVEL SECURITY;
ALTER TABLE solver_configs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE resolutions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE time_windows         ENABLE ROW LEVEL SECURITY;
ALTER TABLE schedule_entries     ENABLE ROW LEVEL SECURITY;
ALTER TABLE solution_comparisons ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs           ENABLE ROW LEVEL SECURITY;

-- Fonction utilitaire : extraire le tenant_id du contexte de session
CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS UUID AS $$
BEGIN
    RETURN current_setting('app.current_tenant_id', TRUE)::UUID;
EXCEPTION
    WHEN OTHERS THEN RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Politique RLS générique : chaque tenant ne voit que ses données
-- (répétée pour chaque table)

CREATE POLICY tenant_isolation ON users
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON machines
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON problem_instances
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON jobs
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON operations
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON setup_times
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON solver_configs
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON resolutions
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON time_windows
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON schedule_entries
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON solution_comparisons
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation ON audit_logs
    USING (tenant_id = current_tenant_id());

-- Politique spéciale pour tenants : un tenant ne peut voir que lui-même
CREATE POLICY tenant_self ON tenants
    USING (id = current_tenant_id());

-- =============================================================================
-- RÔLES POSTGRESQL
-- =============================================================================

-- Rôle applicatif (utilisé par FastAPI)
CREATE ROLE ordosaas_app LOGIN PASSWORD 'change_in_production';
GRANT CONNECT ON DATABASE ordosaas TO ordosaas_app;
GRANT USAGE ON SCHEMA public TO ordosaas_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ordosaas_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO ordosaas_app;

-- Rôle de migration (utilisé par Alembic)
CREATE ROLE ordosaas_migration LOGIN PASSWORD 'change_in_production';
GRANT ALL ON DATABASE ordosaas TO ordosaas_migration;

-- =============================================================================
-- TRIGGERS — Mise à jour automatique de updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_instances_updated_at
    BEFORE UPDATE ON problem_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_resolutions_updated_at
    BEFORE UPDATE ON resolutions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- TRIGGER — Mise à jour auto des stats de l'instance après ajout de jobs
-- =============================================================================

CREATE OR REPLACE FUNCTION update_instance_stats()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE problem_instances
    SET
        nb_jobs = (SELECT COUNT(*) FROM jobs WHERE instance_id = NEW.instance_id),
        updated_at = NOW()
    WHERE id = NEW.instance_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_jobs_update_instance_stats
    AFTER INSERT OR DELETE ON jobs
    FOR EACH ROW EXECUTE FUNCTION update_instance_stats();

CREATE OR REPLACE FUNCTION update_instance_ops_stats()
RETURNS TRIGGER AS $$
DECLARE
    v_instance_id UUID;
BEGIN
    SELECT instance_id INTO v_instance_id FROM jobs WHERE id = NEW.job_id;
    UPDATE problem_instances
    SET
        nb_operations = (
            SELECT COUNT(*) FROM operations o
            JOIN jobs j ON o.job_id = j.id
            WHERE j.instance_id = v_instance_id
        ),
        nb_machines = (
            SELECT COUNT(DISTINCT o.machine_id) FROM operations o
            JOIN jobs j ON o.job_id = j.id
            WHERE j.instance_id = v_instance_id
        ),
        updated_at = NOW()
    WHERE id = v_instance_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_operations_update_instance_stats
    AFTER INSERT OR DELETE ON operations
    FOR EACH ROW EXECUTE FUNCTION update_instance_ops_stats();

-- =============================================================================
-- DONNÉES INITIALES (seed)
-- =============================================================================

-- Tenant de démonstration
INSERT INTO tenants (id, name, slug, default_wr, default_strategy)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'ENSIAS Demo',
    'ensias-demo',
    5,
    'auto'
);

-- Admin de démonstration (mot de passe : 'demo_password' hashé)
INSERT INTO users (id, tenant_id, email, password_hash, first_name, last_name, role, status)
VALUES (
    'b0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'admin@ensias-demo.ma',
    crypt('demo_password', gen_salt('bf')),
    'Abdeladim',
    'El Gouryani',
    'admin',
    'active'
);

-- =============================================================================
-- VUES UTILES
-- =============================================================================

-- Vue résumé des résolutions (pour le dashboard)
CREATE VIEW v_resolution_summary AS
SELECT
    r.id,
    r.tenant_id,
    r.instance_id,
    pi.name AS instance_name,
    pi.nb_jobs,
    pi.nb_machines,
    r.status,
    r.method_used,
    r.total_weighted_tardiness,
    r.nb_jobs_late,
    r.improvement_vs_atcs_pct,
    r.duration_seconds,
    r.created_at,
    u.first_name || ' ' || u.last_name AS triggered_by_name
FROM resolutions r
JOIN problem_instances pi ON r.instance_id = pi.id
JOIN users u ON r.triggered_by = u.id;

-- Vue planning complet pour le Gantt
CREATE VIEW v_gantt_data AS
SELECT
    se.resolution_id,
    se.tenant_id,
    se.job_id,
    j.external_id AS job_external_id,
    j.deadline AS job_deadline,
    j.weight AS job_weight,
    se.machine_id,
    m.external_id AS machine_external_id,
    m.name AS machine_name,
    se.start_time,
    se.end_time,
    se.setup_from_job_id,
    se.setup_start_time,
    se.setup_end_time,
    se.setup_duration,
    se.job_completion_time,
    se.job_tardiness,
    tw.window_index,
    tw.status AS window_status
FROM schedule_entries se
JOIN jobs j ON se.job_id = j.id
JOIN machines m ON se.machine_id = m.id
LEFT JOIN time_windows tw ON se.window_id = tw.id;

-- =============================================================================
-- FIN DU SCHÉMA
-- =============================================================================
