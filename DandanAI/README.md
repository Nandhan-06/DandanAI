# DandanAI — National AI Legal Intelligence Platform (with DandanAI Criminal Intelligence Engine)

Multi-tenant legal-tech web application: case management, document intelligence, Bharat legal research (hybrid RAG with citation verification), a LangGraph multi-agent assessment workflow with human approval, the DandanAI criminal intelligence engine, chat with voice/avatar adapters, a source-coverage dashboard, admin and audit.

> **Honest status:** everything runs locally with deterministic **mock** AI and a **synthetic** legal corpus. No real Indian law ships in this repo, nothing has been run against a live Neon database, and no live LLM/embedding/STT/TTS provider has been exercised. See `BUILD_STATUS.md` and `docs/REQUIREMENTS_TRACEABILITY.md`. It is decision support for advocates, not legal advice.

## 1. Add your external links (the `.env` file)
```bash
cp .env.example .env
```
Fill in at minimum: `DATABASE_URL` (Neon **pooled** string), `DIRECT_URL` (Neon **direct** string), `JWT_SECRET_KEY` (`openssl rand -hex 32`), `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`.
Optional (leave `mock` to stay free): `LLM_PROVIDER`/`LLM_API_KEY`, `EMBEDDING_PROVIDER`, `OCR_PROVIDER`, `STT_*`, `TTS_*`, `AVATAR_*`, `S3_*`, `LANGFUSE_*`, `NEXT_PUBLIC_API_URL`, `CORS_ORIGINS`. Every variable is documented inline in `.env.example`.

## 2. Neon setup
1. Create a Neon project; copy the **pooled** (host has `-pooler`) and **direct** connection strings into `DATABASE_URL` / `DIRECT_URL` (`?sslmode=require`).
2. `bash scripts/setup.sh` (venv + npm install), then `bash scripts/migrate.sh` — runs `alembic upgrade head` over DIRECT_URL: creates the `vector` extension, 26 tables, HNSW + GIN indexes.
3. Start the app; `GET /api/v1/system/status` should show `database.state = CONNECTED`. Optionally verify with `NEON_TEST_DIRECT_URL=<a disposable Neon branch> pytest backend/tests/test_neon_live.py`.
4. If you change `EMBEDDING_DIM` or switch to a real embedding model, re-generate the migration (`python scripts/gen_migration.py`) on a fresh branch and re-embed content.

## 3. Run
```bash
bash scripts/dev.sh               # backend http://localhost:8000 (docs at /docs), frontend http://localhost:3000
# or Docker (needs Docker; not tested in the build environment):
docker compose run --rm migrate && docker compose up --build
```
Sign in with the bootstrap admin, create users under **Admin**, or register advocates at `/register` (admins can never self-register). With `SEED_SYNTHETIC_CORPUS=true` the synthetic test corpus loads at startup so research/agents have something to retrieve; set it `false` once you ingest real material.

## 4. Test (no keys, no Neon needed)
```bash
bash scripts/test_all.sh          # prints PASSED / FAILED / BLOCKED / NOT RUN per stage
cd backend && pytest -q           # 22 tests; uses mocks + an ephemeral TEST database (APP_ENV=test only)
bash scripts/virtual_e2e.sh       # real-HTTP E2E: backend + built frontend, 23 checks
```

## 5. Layout
`backend/` FastAPI app (`app/api`, `app/services`, `app/agents`), Alembic (`alembic/`), tests · `frontend/` Next.js 14 · `docker/` + `docker-compose.yml` · `.github/workflows/ci.yml` · `infra/terraform/` (prepared, applies nothing by default) · `docs/` architecture, API (88 operations), traceability, security · `scripts/`.

## 6. Going live checklist
Real Neon + migrations → real LLM/embedding keys → ingest **permitted** official legal sources and human-verify them (the registry, licence notes and verification workflow are in **Source coverage**) → verify DandanAI's candidate provision table against India Code → install Tesseract for OCR → switch to httpOnly-cookie auth and a durable job queue (`docs/SECURITY.md`) → set `APP_ENV=production`.
