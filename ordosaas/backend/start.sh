#!/bin/bash
set -e

echo "Running database migrations..."
cd /app
alembic upgrade head 2>&1 || echo "Migration failed (may already be applied)"

echo "Running seed..."
python -m app.seed 2>&1 || echo "Seed skipped"

echo "Starting server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
