"""Cree les 9 index specifies par schema_bdd.sql et absents de la base.

Audit du 2026-09-17 (categorie A). La migration 0001 cree 13 index la ou le
schema de conception en specifie 29. Pour les 7 tables auditees, 9 manquent :

    jobs               tenant_id
    operations         machine_id, tenant_id
    setup_times        from_job_id, to_job_id, machine_id
    schedule_entries   job_id, tenant_id, (resolution_id, machine_id, start_time)

Tous portent sur une cle etrangere ou sur tenant_id, colonne de filtrage de toute
requete multi-tenant. Le dernier est le composite explicitement justifie dans le
schema pour la requete Gantt.

Aucun resultat de requete ne change : c'est ce qui rend cette correction sure.

Les noms suivent la convention de la MIGRATION (idx_jobs_tenant) et non celle du
schema (idx_jobs_tenant_id), pour rester coherents avec les 13 index existants.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

INDEX = [
    ("idx_jobs_tenant", "jobs", "tenant_id"),
    ("idx_operations_machine", "operations", "machine_id"),
    ("idx_operations_tenant", "operations", "tenant_id"),
    ("idx_setups_from_job", "setup_times", "from_job_id"),
    ("idx_setups_to_job", "setup_times", "to_job_id"),
    ("idx_setups_machine", "setup_times", "machine_id"),
    ("idx_entries_job", "schedule_entries", "job_id"),
    ("idx_entries_tenant", "schedule_entries", "tenant_id"),
    ("idx_entries_gantt", "schedule_entries", "resolution_id, machine_id, start_time"),
]


def upgrade() -> None:
    for nom, table, colonnes in INDEX:
        op.execute(f"CREATE INDEX IF NOT EXISTS {nom} ON {table}({colonnes})")


def downgrade() -> None:
    for nom, _table, _colonnes in INDEX:
        op.execute(f"DROP INDEX IF EXISTS {nom}")
