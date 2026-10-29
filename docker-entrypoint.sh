#!/bin/sh
set -e

# Optionally apply database migrations before starting the app.
# Enable with RUN_MIGRATIONS=true (runs once, before uvicorn spawns workers).
if [ "${RUN_MIGRATIONS}" = "true" ]; then
    echo "Running database migrations..."
    alembic upgrade head
fi

exec "$@"
