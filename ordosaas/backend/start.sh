#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Running seed data..."
python -m app.seed || echo "Seed already applied or failed (non-blocking)"

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
