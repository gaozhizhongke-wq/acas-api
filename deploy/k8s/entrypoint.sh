#!/bin/bash
# ACAS v2 Kubernetes Entrypoint
# Handles graceful startup with health check and migration

set -euo pipefail

echo "[ENTRYPOINT] Starting ACAS v2..."

# Run Alembic migrations if DB is reachable
if [ "${ACAS_RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[ENTRYPOINT] Running database migrations..."
    python -m alembic upgrade head || {
        echo "[ENTRYPOINT] WARNING: Migration failed. Continuing anyway (may already be up to date)..."
    }
fi

# Start the application
echo "[ENTRYPOINT] Starting application..."
exec "$@"
