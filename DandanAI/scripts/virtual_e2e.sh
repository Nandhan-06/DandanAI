#!/usr/bin/env bash
# Virtual full-stack validation with NO real keys and NO Neon: ephemeral test DB + mock providers.
set -eo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export APP_ENV=test ALLOW_EPHEMERAL_TEST_DB=true DATABASE_URL= DIRECT_URL= STORAGE_DIR="$(mktemp -d)" JWT_SECRET_KEY=virtual-e2e-secret-virtual-e2e-secret CORS_ORIGINS=http://localhost:3000 OCR_PROVIDER=mock
cd "$ROOT/backend" && (python -m uvicorn app.main:app --port 8000 >/tmp/dandanai-api.log 2>&1 &)
WEB=""
if [ -d "$ROOT/frontend/.next" ]; then cd "$ROOT/frontend" && (NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx next start -p 3000 >/tmp/dandanai-web.log 2>&1 &) ; WEB="http://127.0.0.1:3000"; fi
for i in $(seq 1 40); do curl -sf http://127.0.0.1:8000/health >/dev/null && break || sleep 0.5; done
rc=0; python "$ROOT/scripts/e2e_smoke.py" http://127.0.0.1:8000 $WEB || rc=$?
pkill -f "uvicorn app.main:app" || true; pkill -f "next start" || true; pkill -f "next-server" || true
exit $rc
