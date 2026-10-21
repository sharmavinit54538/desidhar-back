#!/bin/sh
set -e

echo "=================================================="
echo " Starting DesiDhar Backend Production Container  "
echo "=================================================="

# 1. Run Alembic Database Migrations
echo "==> [1/3] Applying Database Migrations (alembic upgrade head)..."
alembic upgrade head

# 2. Run Database Seeding
echo "==> [2/3] Seeding Initial Database Data (python -m app.db.seed)..."
python -m app.db.seed

# 3. Start Production Server with Gunicorn and Uvicorn Workers
echo "==> [3/3] Starting Gunicorn server on 0.0.0.0:8000 with 4 Uvicorn workers..."
exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --workers 4 \
  --access-logfile - \
  --error-logfile - \
  --graceful-timeout 30 \
  --timeout 60 \
  --keep-alive 5
