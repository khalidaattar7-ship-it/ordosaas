"""Add tenant sector, solver stability_weight, and the sector_defaults reference table.

Le secteur sert uniquement a PROPOSER un socle de configuration a un nouveau tenant
(cf. app/sectors.py) ; rien n'est applique automatiquement.

Les valeurs semees ci-dessous sont des HYPOTHESES tirees d'indices structurels sur les
secteurs industriels marocains, sans aucune donnee quantifiee a l'appui. Elles vivent en
base precisement pour qu'un ajustement soit un UPDATE et non un deploiement. La colonne
`rationale` conserve la raison de chaque choix, pour qu'on sache plus tard ce qu'on
reexamine.

`stability_weight` est ajoute a `solver_configs` : il est absent du schema de conception
d'origine parce qu'il est ne apres lui, avec l'architecture incrementale. Sans cette
colonne, les secteurs `cablage_auto` et `textile` — ceux ou le signal etait le plus net —
n'auraient aucun levier distinctif.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-12
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


SECTEURS_SQL = (
    "'cablage_auto', 'plasturgie', 'agro_alimentaire', "
    "'textile', 'sous_traitance_mecanique', 'autre'"
)

SCHEMA_SQL = rf"""
ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS sector VARCHAR(30) NOT NULL DEFAULT 'autre';

ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenant_sector;
ALTER TABLE tenants ADD CONSTRAINT ck_tenant_sector
    CHECK (sector IN ({SECTEURS_SQL}));

ALTER TABLE solver_configs
    ADD COLUMN IF NOT EXISTS stability_weight NUMERIC(6,4) NOT NULL DEFAULT 0.1;

ALTER TABLE solver_configs DROP CONSTRAINT IF EXISTS ck_cfg_stability;
ALTER TABLE solver_configs ADD CONSTRAINT ck_cfg_stability
    CHECK (stability_weight >= 0);

CREATE TABLE IF NOT EXISTS sector_defaults (
    sector           VARCHAR(30) PRIMARY KEY
                     CHECK (sector IN ({SECTEURS_SQL})),
    wr               INTEGER NOT NULL CHECK (wr BETWEEN 1 AND 50),
    stability_weight NUMERIC(6,4) NOT NULL CHECK (stability_weight >= 0),
    cpsat_timeout    INTEGER NOT NULL CHECK (cpsat_timeout BETWEEN 5 AND 300),
    strategy         VARCHAR(10) NOT NULL
                     CHECK (strategy IN ('auto','cpsat','lns','atcs')),
    rationale        TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# wr=5, stability_weight=0.1, cpsat_timeout=30, strategy='auto' sont les defauts
# ACTUELS du projet : tout ecart ci-dessous est une hypothese assumee, tout alignement
# sur ces valeurs est une absence deliberee de supposition.
SEED_SQL = r"""
INSERT INTO sector_defaults (sector, wr, stability_weight, cpsat_timeout, strategy, rationale)
VALUES
    ('cablage_auto', 5, 0.3000, 30, 'auto',
     'HYPOTHESE non validee : flux JIS, insertions urgentes frequentes. Un poids de '
     'stabilite releve (0.3 au lieu de 0.1) vise a limiter le bouleversement du '
     'planning a chaque insertion. Aucune donnee marocaine quantifiee a l''appui.'),
    ('textile', 5, 0.3000, 30, 'auto',
     'HYPOTHESE non validee : fast-fashion, reordonnancements frequents sur commande. '
     'Meme raisonnement que le cablage automobile. Aucune donnee quantifiee.'),
    ('plasturgie', 8, 0.1000, 30, 'auto',
     'HYPOTHESE non validee : aleas subis dominants (pannes courtes frequentes, '
     'changements de serie longs). Davantage de techniciens setup (wr 8 au lieu de 5) '
     'pour absorber les changements. Aucune donnee quantifiee.'),
    ('sous_traitance_mecanique', 6, 0.1000, 30, 'auto',
     'HYPOTHESE non validee : profil mixte penchant vers les aleas subis, moins marque '
     'que la plasturgie. Aucune donnee quantifiee.'),
    ('agro_alimentaire', 5, 0.1000, 30, 'auto',
     'Profil mixte sans signal net : defauts actuels du projet conserves. Aucune '
     'supposition, donc rien a reviser tant qu''aucune donnee ne contredit ce choix.'),
    ('autre', 5, 0.1000, 30, 'auto',
     'Secteur par defaut. Defauts actuels du projet, aucune supposition.')
ON CONFLICT (sector) DO NOTHING;
"""


def upgrade() -> None:
    op.execute(SCHEMA_SQL)
    op.execute(SEED_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sector_defaults CASCADE;")
    op.execute("ALTER TABLE solver_configs DROP CONSTRAINT IF EXISTS ck_cfg_stability;")
    op.execute("ALTER TABLE solver_configs DROP COLUMN IF EXISTS stability_weight;")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenant_sector;")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS sector;")
