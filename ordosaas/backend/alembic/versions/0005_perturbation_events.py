"""Add perturbation_events and the incremental columns on resolutions.

Rend persistante la dataclass `PerturbationEvent`, jusqu'ici purement en memoire
(decision D5). Les deux coexistent : la dataclass circule dans le coeur scheduling, qui
reste sans dependance base (D9) ; cette table journalise ce qui a ete traite.

Complete aussi `resolutions` des trois colonnes que le schema de conception prevoyait et
que le modele SQLAlchemy n'avait jamais recues — ecart identifie par la cartographie du
2026-09-12.

`base_resolution_id` et `reported_by` sont NON NULS, conformement au schema de
conception. Un evenement d'origine automatisee (futur connecteur MES) sera attribue a un
COMPTE DE SERVICE dans `users`, pas a un champ nul : ce cas ne demandera aucune
migration.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-12
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


TYPES_SQL = (
    "'machine_breakdown', 'urgent_job', 'duration_change', "
    "'job_cancel', 'resource_change'"
)

SCHEMA_SQL = rf"""
ALTER TABLE resolutions
    ADD COLUMN IF NOT EXISTS parent_resolution_id UUID REFERENCES resolutions(id);
ALTER TABLE resolutions
    ADD COLUMN IF NOT EXISTS trigger_type VARCHAR(20) NOT NULL DEFAULT 'manual';
ALTER TABLE resolutions
    ADD COLUMN IF NOT EXISTS nb_jobs_affected INTEGER;

ALTER TABLE resolutions DROP CONSTRAINT IF EXISTS ck_resolution_trigger_type;
ALTER TABLE resolutions ADD CONSTRAINT ck_resolution_trigger_type
    CHECK (trigger_type IN ('manual', 'incremental', 'scheduled'));

CREATE TABLE IF NOT EXISTS perturbation_events (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    base_resolution_id      UUID NOT NULL REFERENCES resolutions(id),
    triggered_resolution_id UUID REFERENCES resolutions(id),
    event_type              VARCHAR(30) NOT NULL
                            CHECK (event_type IN ({TYPES_SQL})),
    payload                 JSONB NOT NULL,
    reported_by             UUID NOT NULL REFERENCES users(id),
    event_timestamp         INTEGER,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_perturbation_tenant ON perturbation_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_perturbation_type ON perturbation_events(event_type);
CREATE INDEX IF NOT EXISTS idx_perturbation_created ON perturbation_events(created_at);
"""


def upgrade() -> None:
    op.execute(SCHEMA_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS perturbation_events CASCADE;")
    op.execute(
        "ALTER TABLE resolutions DROP CONSTRAINT IF EXISTS ck_resolution_trigger_type;"
    )
    op.execute("ALTER TABLE resolutions DROP COLUMN IF EXISTS nb_jobs_affected;")
    op.execute("ALTER TABLE resolutions DROP COLUMN IF EXISTS trigger_type;")
    op.execute("ALTER TABLE resolutions DROP COLUMN IF EXISTS parent_resolution_id;")
