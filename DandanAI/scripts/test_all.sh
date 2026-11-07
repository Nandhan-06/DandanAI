#!/usr/bin/env bash
# Reproducible test run. Prints PASSED / FAILED / BLOCKED / NOT RUN per stage. Uses mocks + ephemeral TEST db (never Neon).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; PY="$ROOT/backend/.venv/bin/python"; [ -x "$PY" ] || PY=python3
res() { printf "%-34s %s\n" "$1" "$2"; }
cd "$ROOT/backend"
$PY -m ruff check app tests >/dev/null 2>&1 && res "backend lint (ruff)" PASSED || res "backend lint (ruff)" "FAILED (or ruff not installed)"
$PY -m pytest -q >/tmp/pytest.out 2>&1 && res "backend tests (pytest)" "PASSED ($(tail -1 /tmp/pytest.out))" || res "backend tests (pytest)" FAILED
DATABASE_URL= $PY -m alembic upgrade head --sql >/dev/null 2>&1 && res "migration SQL generation (offline)" PASSED || res "migration SQL generation (offline)" FAILED
if [ -n "$NEON_TEST_DIRECT_URL" ]; then NEON_TEST_DIRECT_URL="$NEON_TEST_DIRECT_URL" $PY -m pytest -q tests/test_neon_live.py >/dev/null 2>&1 && res "LIVE Neon integration" PASSED || res "LIVE Neon integration" FAILED
else res "LIVE Neon integration" "BLOCKED (set NEON_TEST_DIRECT_URL to a disposable Neon branch)"; fi
cd "$ROOT/frontend"
if [ -d node_modules ]; then npx tsc --noEmit >/dev/null 2>&1 && res "frontend typecheck" PASSED || res "frontend typecheck" FAILED
  npm run build >/dev/null 2>&1 && res "frontend build" PASSED || res "frontend build" FAILED; else res "frontend typecheck/build" "NOT RUN (npm install first)"; fi
cd "$ROOT"; bash scripts/virtual_e2e.sh >/tmp/e2e.out 2>&1 && res "virtual E2E over HTTP" "PASSED ($(tail -1 /tmp/e2e.out))" || res "virtual E2E over HTTP" FAILED
res "browser UI interaction tests" "NOT RUN (no browser automation in this build)"
res "docker build / compose up" "NOT RUN (Docker unavailable in build environment)"
