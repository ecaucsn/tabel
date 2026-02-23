#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."

# Timeout for waiting PostgreSQL (in seconds)
TIMEOUT=${DB_WAIT_TIMEOUT:-30}
count=0

while ! nc -z $DB_HOST $DB_PORT; do
  sleep 0.1
  count=$((count + 1))
  if [ $count -ge $((TIMEOUT * 10)) ]; then
    echo "ERROR: Timeout waiting for PostgreSQL at $DB_HOST:$DB_PORT"
    exit 1
  fi
done
echo "PostgreSQL is up!"

echo "Running migrations..."
if ! python manage.py migrate --noinput; then
  echo "ERROR: Migration failed!"
  exit 1
fi

echo "Collecting static files..."
if ! python manage.py collectstatic --noinput; then
  echo "WARNING: Collectstatic failed, continuing anyway..."
fi

echo "Starting server..."
exec gunicorn --bind 0.0.0.0:8000 --workers 2 config.wsgi:application
