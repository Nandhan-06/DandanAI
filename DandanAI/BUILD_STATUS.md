# BUILD_STATUS

Built and validated in a sandbox with **no Neon, no API keys, no Docker, no browser automation**. Dates: 2026-10-31.

## Test results (reproduce with `bash scripts/test_all.sh`)
| Stage | Result |
|---|---|
| Backend lint (ruff) | PASSED |
| Backend tests (pytest, 22 tests) | PASSED — 22 passed, 1 skipped (live Neon) |
| Migration SQL generation, offline (`alembic upgrade head --sql`) | PASSED (26 tables + pgvector + HNSW + GIN). **Not executed on a PostgreSQL server.** |
| Live Neon integration (`tests/test_neon_live.py`) | **BLOCKED** — needs `NEON_TEST_DIRECT_URL` |
| Frontend typecheck (`tsc --noEmit`) | PASSED |
| Frontend production build (`next build`, 15 routes) | PASSED |
| Virtual E2E over real HTTP (backend + built frontend, 23 checks) | PASSED |
| Browser UI interaction tests (clicks, forms, mic, audio) | **NOT RUN** |
| Docker build / compose up | **NOT RUN** |
| `terraform validate` | **NOT RUN** |
| OpenAI/Gemini/S3/Langfuse/Tesseract adapters | **NOT RUN** (no credentials / binaries) |

Tests use deterministic mocks and an explicitly labelled ephemeral SQLite test database (APP_ENV=test only). That is **not** evidence that Neon works.

## Mocked (clearly labelled in UI, API and reports)
LLM, embeddings (hashed bag-of-words), OCR (when Tesseract absent), STT, TTS (tone sequence), avatar (viseme timeline), legal corpus (**all legal text is synthetic test data**).

## Not built / partial
Automated ingestion from official portals (needs licence/terms review), knowledge-graph store, quantum-inspired retrieval (not justified), multilingual, password-reset email flow, real STT/TTS/avatar vendors, cross-encoder reranker, background worker queue (FastAPI BackgroundTasks used), rate limiting beyond a per-process login throttle.

## Legal-content caveats
* No real Indian statute/judgment text ships with this repo. The corpus in `services/corpus.py` is fictional and flagged `SYNTHETIC`.
* DandanAI's candidate offence table (`agents/criminal.py`) contains section references written from general background knowledge; they are labelled *candidate (unverified)* and are never presented as verified. Verify them against India Code before any reliance.
* Punishment/compensation text is only ever quoted from retrieved sources; with no real verified source the report says "NOT VERIFIED".
* Coverage dashboard states the nationwide coverage audit is NOT PERFORMED.
