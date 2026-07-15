#!/bin/sh
# ACAS v2 startup entrypoint
# 1. Wait for PostgreSQL to be ready
# 2. Run Alembic migrations (idempotent)
# 3. Start the API server

echo "[startup] Waiting for PostgreSQL at ${ACAS_DB_HOST}:${ACAS_DB_PORT}..."

# Wait for PostgreSQL to be ready
until PGPASSWORD="${ACAS_DB_PASSWORD}" psql \
    -h "${ACAS_DB_HOST}" \
    -p "${ACAS_DB_PORT}" \
    -U "${ACAS_DB_USER}" \
    -d "${ACAS_DB_NAME}" \
    -c '\q' 2>/dev/null; do
    echo "[startup] PostgreSQL not ready, retrying in 5s..."
    sleep 5
done

echo "[startup] PostgreSQL is ready!"

# Build the full DB URL and export it so python run.py picks it up
# (psql also needs PGPASSWORD for its own auth)
export ACAS_DB_URL="postgresql+psycopg://${ACAS_DB_USER}:${ACAS_DB_PASSWORD}@${ACAS_DB_HOST}:${ACAS_DB_PORT}/${ACAS_DB_NAME}"
export PGPASSWORD="${ACAS_DB_PASSWORD}"

# Run Alembic migrations
echo "[startup] Running Alembic migrations..."
alembic upgrade head || {
    echo "[startup] ERROR: Alembic migration failed!"
    exit 1
}

# Start the API (exec replaces the shell so the app gets PID 1 / proper signals)
echo "[startup] Starting ACAS API..."
exec python run.py
