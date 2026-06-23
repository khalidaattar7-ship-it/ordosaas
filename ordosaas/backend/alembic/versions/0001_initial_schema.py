"""Initial schema for OrdoSaaS.

Revision ID: 0001
Revises:
Create Date: 2026-06-23
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


SCHEMA_SQL = r"""
-- ============================================================
--  OrdoSaaS — schema initial
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------- tenants ----------
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    default_wr INTEGER NOT NULL DEFAULT 5 CHECK (default_wr BETWEEN 1 AND 50),
    default_timeout INTEGER NOT NULL DEFAULT 30 CHECK (default_timeout BETWEEN 5 AND 300),
    default_strategy VARCHAR(10) NOT NULL DEFAULT 'auto'
        CHECK (default_strategy IN ('auto','cpsat','lns','atcs')),
    max_jobs_per_instance INTEGER NOT NULL DEFAULT 500,
    max_machines_per_instance INTEGER NOT NULL DEFAULT 20,
    max_instances_stored INTEGER NOT NULL DEFAULT 100,
    timezone VARCHAR(50) NOT NULL DEFAULT 'Africa/Casablanca',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- users ----------
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255),
    first_name VARCHAR(100) NOT NULL DEFAULT '',
    last_name VARCHAR(100) NOT NULL DEFAULT '',
    role VARCHAR(20) NOT NULL DEFAULT 'lecteur'
        CHECK (role IN ('admin','planificateur','lecteur')),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('active','inactive','pending')),
    invitation_token VARCHAR(255),
    invitation_expires TIMESTAMPTZ,
    reset_token VARCHAR(255),
    reset_expires TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_tenant_email UNIQUE (tenant_id, email)
);
CREATE INDEX idx_users_tenant ON users(tenant_id);

-- ---------- machines ----------
CREATE TABLE machines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_id VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','maintenance','inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_machine_tenant_external UNIQUE (tenant_id, external_id)
);
CREATE INDEX idx_machines_tenant ON machines(tenant_id);

-- ---------- problem_instances ----------
CREATE TABLE problem_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    nb_jobs INTEGER NOT NULL DEFAULT 0,
    nb_machines INTEGER NOT NULL DEFAULT 0,
    nb_operations INTEGER NOT NULL DEFAULT 0,
    nb_setups INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','solving','solved','error')),
    import_source VARCHAR(20) NOT NULL DEFAULT 'csv'
        CHECK (import_source IN ('csv','manual','demo')),
    raw_jobs_csv TEXT,
    raw_operations_csv TEXT,
    raw_setups_csv TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_instances_tenant ON problem_instances(tenant_id);

-- ---------- jobs ----------
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    instance_id UUID NOT NULL REFERENCES problem_instances(id) ON DELETE CASCADE,
    external_id VARCHAR(100) NOT NULL,
    deadline INTEGER NOT NULL CHECK (deadline > 0),
    weight NUMERIC(10,4) NOT NULL DEFAULT 1.0 CHECK (weight > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_job_instance_external UNIQUE (instance_id, external_id)
);
CREATE INDEX idx_jobs_instance ON jobs(instance_id);

-- ---------- operations ----------
CREATE TABLE operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    machine_id UUID NOT NULL REFERENCES machines(id),
    position INTEGER NOT NULL CHECK (position >= 1),
    duration INTEGER NOT NULL CHECK (duration > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_operation_job_position UNIQUE (job_id, position),
    CONSTRAINT uq_operation_job_machine UNIQUE (job_id, machine_id)
);
CREATE INDEX idx_operations_job ON operations(job_id);

-- ---------- setup_times ----------
CREATE TABLE setup_times (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    instance_id UUID NOT NULL REFERENCES problem_instances(id) ON DELETE CASCADE,
    from_job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    to_job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    machine_id UUID NOT NULL REFERENCES machines(id),
    duration INTEGER NOT NULL DEFAULT 0 CHECK (duration >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_setup_unique UNIQUE (instance_id, from_job_id, to_job_id, machine_id)
);
CREATE INDEX idx_setups_instance ON setup_times(instance_id);

-- ---------- solver_configs ----------
CREATE TABLE solver_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    instance_id UUID NOT NULL REFERENCES problem_instances(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    wr INTEGER NOT NULL DEFAULT 5 CHECK (wr BETWEEN 1 AND 50),
    strategy VARCHAR(10) NOT NULL DEFAULT 'auto'
        CHECK (strategy IN ('auto','cpsat','lns','atcs')),
    cpsat_timeout INTEGER NOT NULL DEFAULT 30 CHECK (cpsat_timeout BETWEEN 5 AND 300),
    max_jobs_per_window INTEGER NOT NULL DEFAULT 50 CHECK (max_jobs_per_window BETWEEN 5 AND 200),
    min_jobs_per_window INTEGER NOT NULL DEFAULT 5 CHECK (min_jobs_per_window BETWEEN 2 AND 20),
    max_recursion_depth INTEGER NOT NULL DEFAULT 4 CHECK (max_recursion_depth BETWEEN 1 AND 8),
    max_iterations INTEGER NOT NULL DEFAULT 5 CHECK (max_iterations BETWEEN 1 AND 20),
    epsilon NUMERIC(6,4) NOT NULL DEFAULT 0.01,
    junction_radius INTEGER NOT NULL DEFAULT 10 CHECK (junction_radius BETWEEN 2 AND 30),
    k1 NUMERIC(6,4),
    k2 NUMERIC(6,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_configs_instance ON solver_configs(instance_id);

-- ---------- resolutions ----------
CREATE TABLE resolutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    instance_id UUID NOT NULL REFERENCES problem_instances(id) ON DELETE CASCADE,
    config_id UUID NOT NULL REFERENCES solver_configs(id),
    triggered_by UUID NOT NULL REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','completed','partial','failed','cancelled')),
    method_used VARCHAR(10) CHECK (method_used IN ('cpsat','lns','atcs') OR method_used IS NULL),
    total_weighted_tardiness NUMERIC(15,4),
    nb_jobs_late INTEGER,
    nb_jobs_on_time INTEGER,
    max_tardiness NUMERIC(15,4),
    machine_utilization_pct NUMERIC(6,2),
    total_setup_time INTEGER,
    atcs_weighted_tardiness NUMERIC(15,4),
    improvement_vs_atcs_pct NUMERIC(6,2),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_seconds NUMERIC(10,3),
    progress_pct INTEGER NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    current_phase INTEGER NOT NULL DEFAULT 0 CHECK (current_phase BETWEEN 0 AND 4),
    progress_detail JSONB,
    error_message TEXT,
    error_detail JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_resolutions_instance ON resolutions(instance_id);
CREATE INDEX idx_resolutions_tenant ON resolutions(tenant_id);

-- ---------- time_windows ----------
CREATE TABLE time_windows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    resolution_id UUID NOT NULL REFERENCES resolutions(id) ON DELETE CASCADE,
    window_index INTEGER NOT NULL CHECK (window_index >= 1),
    t_start INTEGER NOT NULL CHECK (t_start >= 0),
    t_end INTEGER NOT NULL CHECK (t_end > t_start),
    nb_jobs INTEGER NOT NULL CHECK (nb_jobs > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','optimal','feasible','atcs_fallback','error')),
    method_used VARCHAR(20),
    recursion_depth INTEGER NOT NULL DEFAULT 0,
    local_weighted_tardiness NUMERIC(15,4),
    duration_seconds NUMERIC(10,3),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_windows_resolution ON time_windows(resolution_id);

-- ---------- schedule_entries ----------
CREATE TABLE schedule_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    resolution_id UUID NOT NULL REFERENCES resolutions(id) ON DELETE CASCADE,
    operation_id UUID NOT NULL REFERENCES operations(id),
    job_id UUID NOT NULL REFERENCES jobs(id),
    machine_id UUID NOT NULL REFERENCES machines(id),
    window_id UUID REFERENCES time_windows(id),
    start_time INTEGER NOT NULL CHECK (start_time >= 0),
    end_time INTEGER NOT NULL CHECK (end_time > start_time),
    setup_from_job_id UUID REFERENCES jobs(id),
    setup_start_time INTEGER,
    setup_end_time INTEGER,
    setup_duration INTEGER NOT NULL DEFAULT 0,
    job_completion_time INTEGER,
    job_tardiness NUMERIC(15,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_entries_resolution ON schedule_entries(resolution_id);
CREATE INDEX idx_entries_machine ON schedule_entries(machine_id);

-- ---------- solution_comparisons ----------
CREATE TABLE solution_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    resolution_a_id UUID NOT NULL REFERENCES resolutions(id),
    resolution_b_id UUID NOT NULL REFERENCES resolutions(id),
    delta_weighted_tardiness NUMERIC(15,4),
    delta_jobs_late INTEGER,
    delta_machine_utilization NUMERIC(6,2),
    winner VARCHAR(1) CHECK (winner IN ('A','B') OR winner IS NULL),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_comparisons_tenant ON solution_comparisons(tenant_id);

-- ============================================================
--  Trigger : updated_at auto-refresh
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tenants_updated     BEFORE UPDATE ON tenants            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_users_updated       BEFORE UPDATE ON users              FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_machines_updated    BEFORE UPDATE ON machines           FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_instances_updated   BEFORE UPDATE ON problem_instances  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_resolutions_updated BEFORE UPDATE ON resolutions        FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
--  Vue : recapitulatif des resolutions
-- ============================================================
CREATE VIEW v_resolution_summary AS
SELECT
    r.id,
    r.tenant_id,
    pi.name AS instance_name,
    r.status,
    r.method_used,
    r.total_weighted_tardiness,
    r.nb_jobs_late,
    r.machine_utilization_pct,
    r.improvement_vs_atcs_pct,
    r.duration_seconds,
    r.created_at
FROM resolutions r
JOIN problem_instances pi ON pi.id = r.instance_id;

-- ============================================================
--  Seed : tenant de demonstration + admin
-- ============================================================
INSERT INTO tenants (id, name, slug)
VALUES ('00000000-0000-0000-0000-000000000001', 'Demo Industries', 'demo')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO users (tenant_id, email, first_name, last_name, role, status)
VALUES ('00000000-0000-0000-0000-000000000001', 'admin@demo.ordosaas.ma',
        'Admin', 'Demo', 'admin', 'active')
ON CONFLICT (tenant_id, email) DO NOTHING;
"""


DROP_SQL = r"""
DROP VIEW IF EXISTS v_resolution_summary;
DROP TABLE IF EXISTS solution_comparisons CASCADE;
DROP TABLE IF EXISTS schedule_entries CASCADE;
DROP TABLE IF EXISTS time_windows CASCADE;
DROP TABLE IF EXISTS resolutions CASCADE;
DROP TABLE IF EXISTS solver_configs CASCADE;
DROP TABLE IF EXISTS setup_times CASCADE;
DROP TABLE IF EXISTS operations CASCADE;
DROP TABLE IF EXISTS jobs CASCADE;
DROP TABLE IF EXISTS problem_instances CASCADE;
DROP TABLE IF EXISTS machines CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS tenants CASCADE;
DROP FUNCTION IF EXISTS set_updated_at();
"""


def upgrade() -> None:
    op.execute(SCHEMA_SQL)


def downgrade() -> None:
    op.execute(DROP_SQL)
