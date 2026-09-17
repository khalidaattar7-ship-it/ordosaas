"""Contraint time_windows.method_used, qui ne l'etait nulle part.

Audit du 2026-09-17 (categorie B). OCCURRENCE DU MOTIF RECURRENT deja nomme dans
"Approche & patterns" : une contrainte prevue sur le papier que la base n'applique
pas. Meme famille que H8/H9, D16/D17 et H10a/b/c.

Trois constats empiles :

1. `schema_bdd.sql` declare CHECK (method_used IN ('cpsat','atcs', NULL)). En SQL,
   'zzz' IN ('cpsat','atcs',NULL) vaut NULL, jamais FALSE — et un CHECK qui vaut
   NULL PASSE. La contrainte du document est donc inoperante dans sa propre
   formulation : elle accepte n'importe quelle valeur.
2. La migration 0001 ne portait AUCUN check sur cette colonne, et le modele non
   plus. La colonne etait totalement libre en base.
3. Le projet connaissait deja le piege sans l'avoir generalise : 0001 l'evite pour
   solution_comparisons.winner, et 0003 l'a corrige pour resolutions.method_used —
   parce que le solveur y stockait historiquement 'optimal'/'feasible'.
   time_windows.method_used est le seul endroit ou la lecon n'a jamais ete appliquee.

LA LISTE DU SCHEMA EST PERIMEE, PAS LE CODE. `app/resolutions/service.py:191` ecrit
method_used=schedule.method_used, dont les valeurs reelles sont 'cpsat', 'lns' et
'incremental'. Appliquer litteralement IN ('cpsat','atcs') rejetterait des donnees
legitimes des la premiere resolution LNS aboutie — exactement la situation de
stability_weight : 'lns' et 'incremental' sont nes apres la redaction du schema.

La forme retenue est celle de 0003, la seule qui rejette reellement.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-17
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

CONTRAINTE = (
    "CHECK (method_used IN ('cpsat', 'lns', 'atcs', 'incremental') "
    "OR method_used IS NULL)"
)


def upgrade() -> None:
    op.execute("ALTER TABLE time_windows DROP CONSTRAINT IF EXISTS ck_window_method")
    op.execute(
        f"ALTER TABLE time_windows ADD CONSTRAINT ck_window_method {CONTRAINTE}"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE time_windows DROP CONSTRAINT IF EXISTS ck_window_method")
