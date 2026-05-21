#!/bin/bash
# Convenience script to run the BTHome web server with Gunicorn

# Configuration
HOST="0.0.0.0"
PORT="5000"
WORKERS=${GUNICORN_WORKERS:-4}
THREADS=${GUNICORN_THREADS:-2}
DATABASE=${BTHOME_DATABASE:-"bthome_data.db"}
ENV=${BTHOME_ENV:-"production"}
APP_MOUNT_PATH=${APP_MOUNT_PATH:-"/watering"}

# Export environment variables for the application
export BTHOME_DATABASE="$DATABASE"
export BTHOME_ENV="$ENV"
export APP_MOUNT_PATH="$APP_MOUNT_PATH"

echo "Starting BTHome Web Server with Gunicorn"
echo "========================================="
echo "Database: $DATABASE"
echo "Environment: $ENV"
echo "Mount Path: $APP_MOUNT_PATH"
echo "Binding to: $HOST:$PORT"
echo "Workers: $WORKERS"
echo "Threads per worker: $THREADS"
echo ""

exec gunicorn \
    --bind "$HOST:$PORT" \
    --workers "$WORKERS" \
    --threads "$THREADS" \
    --worker-class gthread \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    wsgi:application
