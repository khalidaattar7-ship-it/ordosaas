"""Ensure resolutions.method_used CHECK constraint accepts solver names.

The CPSAT solver historically stored a result status ('optimal'/'feasible')
in method_used, which violated ck_resolution_method. The application now always
stores the solver name (cpsat/lns/atcs); this migration recreates the constraint
to guarantee it matches the model, regardless of any earlier drifted state.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-25
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE resolutions DROP CONSTRAINT IF EXISTS ck_resolution_method")
    op.execute(
        "ALTER TABLE resolutions ADD CONSTRAINT ck_resolution_method "
        "CHECK (method_used IN ('cpsat', 'lns', 'atcs') OR method_used IS NULL)"
    )


def downgrade() -> None:
    # Constraint definition is unchanged from 0001; nothing to revert.
    pass
