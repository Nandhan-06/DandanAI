#!/usr/bin/env bash
# One-time local setup. Usage: bash scripts/setup.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
[ -f .env ] || { cp .env.example .env; echo "Created .env — edit DATABASE_URL / DIRECT_URL / JWT_SECRET_KEY / BOOTSTRAP_ADMIN_* now."; }
python3 -m venv backend/.venv && backend/.venv/bin/pip install -q -r backend/requirements-dev.txt
(cd frontend && npm install --no-audit --no-fund)
echo "Next: set Neon URLs in .env, then  bash scripts/migrate.sh  and  bash scripts/dev.sh"
