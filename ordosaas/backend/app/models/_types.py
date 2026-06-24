"""Cross-dialect column types.

These aliases let the ORM models run on both PostgreSQL (native UUID / JSONB)
and SQLite (used as a local fallback when Postgres is unavailable). The generic
``Uuid`` and ``JSON`` types compile to native types on Postgres and to
CHAR(32)/JSON-as-text on SQLite.
"""
from sqlalchemy import JSON as _JSON
from sqlalchemy import Uuid as _Uuid

# Drop-in replacements for sqlalchemy.dialects.postgresql.UUID / JSONB.
UUID = _Uuid  # supports UUID(as_uuid=True)
JSONB = _JSON

__all__ = ["UUID", "JSONB"]
