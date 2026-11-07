#!/usr/bin/env bash
# Starts backend (8000) and frontend (3000) for development.
set -e; ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"; [ -x "$PY" ] || PY=python3
(cd "$ROOT/backend" && $PY -m uvicorn app.main:app --reload --port 8000) &
(cd "$ROOT/frontend" && npm run dev) &
wait
