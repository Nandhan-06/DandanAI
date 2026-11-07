# DandanAI — Architecture

```
Browser (Next.js 14 / React / Tailwind)  ──HTTPS+JWT──►  FastAPI (Pydantic, SQLAlchemy 2, Argon2, PyJWT)
                                                           │
        ┌──────────────────────────────────────────────────┼───────────────────────────────────────┐
        │ api/*  routers (auth, admin, cases, documents, research, workflows, reports, chat/voice)  │
        │ deps.py  org + owner/member case authorisation on EVERY case-scoped route                 │
        │ services/ docintel · extraction · rag · corpus/seed · guardrails · reports · providers    │
        │ agents/   LangGraph graphs: case_graph.py (5 agents) · criminal.py (DandanAI, 8 nodes)    │
        └──────────────────────────────────────────────────┬───────────────────────────────────────┘
                                                           ▼
                       Neon PostgreSQL (pooled DATABASE_URL for traffic, DIRECT_URL for Alembic) + pgvector
                       Private object storage (local dir or S3-compatible) for original files; metadata in Neon
```

## Neon-only database
* `app/database.py` builds the engine only from `DATABASE_URL` (normalised to `postgresql+psycopg`, `sslmode=require`, `prepare_threshold=None` for PgBouncer). No SQLite/local-Postgres fallback exists. Without credentials DB routes answer 503 and `/api/v1/system/status` says `BLOCKED_NO_NEON_CREDENTIALS`.
* The automated tests use an explicit ephemeral in-memory database that is only reachable when `APP_ENV=test` **and** `ALLOW_EPHEMERAL_TEST_DB=true`; the status endpoint labels it `EPHEMERAL_TEST_DB_NOT_NEON`, and `create_app()` refuses to boot in production with it enabled.
* Schema: 26 tables (`backend/app/models.py`); migration `0001_initial.py` is generated from the models with the PostgreSQL dialect (`scripts/gen_migration.py`) and adds `CREATE EXTENSION vector`, HNSW cosine indexes on both embedding columns and a GIN full-text index. `EmbeddingType` is `vector(EMBEDDING_DIM)` on PostgreSQL.

## Tenancy & access control
Organisation → Users → Cases. `case_access()` allows only the owner or an explicit `CaseMember` of the same organisation; everyone else (other orgs, same-org non-members, admins) gets 404. Legal assistants can edit shared cases but cannot run assessments or approve reports. Chunks/embeddings of case documents carry `org_id` + `case_id` and are only queried for case IDs the caller may access. Conversations are private to their creator. Audit logs record auth, case, document, workflow, report and admin actions.

## Legal RAG (`services/rag.py`)
Chunking (section-aware, page-aware) → embeddings (provider abstraction; deterministic hashed mock) → storage → **hybrid retrieval**: Okapi BM25 + cosine vector search fused by reciprocal rank fusion, noise-gated (a weak vector hit counts only when lexically corroborated) → reranker interface → citation objects (title, section/pinpoint, court, citation, date, jurisdiction, authority class primary/secondary, verification status, source URL, synthetic flag).
Filters: jurisdiction hierarchy (India + the named State/UT), temporal applicability (`as_of`; commencement/repeal dates; repealed excluded unless historical), instrument type, authority class, stance/offence tags.
Output includes `coverage_gaps` and a categorical `confidence` (none/low/medium/high) — never a probability. Synthetic-only or unverified sources can never reach "sufficient support".
**Citation verification** (`verify_citation`): chunk exists, metadata matches, quoted text appears verbatim, instrument in force on the date, source is real and human-verified. `find_uncited_authorities` flags statute/section mentions with no supporting citation.

## LangGraph agents
Case assessment (`agents/case_graph.py`): **Document Analysis → Legal Research → Case Assessment → Adversarial Review → Citation Verification → human-review gate**. After verification a conditional edge either re-runs assessment with failed citations stripped (max 2 rounds) or proceeds. DandanAI (`agents/criminal.py`): incident analysis → crime classification → statute/element mapping → evidence planner → precedent research (similar + contrary) → punishment/compensation (from retrieved text only) → citation verification → review gate.
`agents/common.py::make_node` gives every agent: typed state (`WorkflowState`), 3-attempt retry policy, per-attempt `WorkflowStep` logs, validation errors, a `WorkflowCheckpoint` after each success, skip-if-completed so `POST /workflows/{id}/resume` continues from the last checkpoint. Runs end `awaiting_review`; only an advocate can approve/reject (`approved`/`rejected`), and the report banner changes from DRAFT to APPROVED.

## Document intelligence
PyMuPDF (page-level), python-docx (single logical page, `docx-body` locator), images through the OCR adapter (Tesseract if installed, otherwise a labelled mock that **does not** inject fake text — the document is marked `extracted_mock_ocr`). Deterministic extractors produce parties, dates, deadlines, amounts, clauses, obligations, legal references, durations, missing information and risks; each row has `origin` = `explicit` (with page) or `ai_inferred`, plus review status (confirm/edit/reject). Versioning via `version_group`; comparison reports clause diffs, financial differences, termination differences, missing clauses, inconsistencies.

## Safety
`services/guardrails.py`: input cleaning (control chars, length, prompt-injection neutralisation), output prediction filter (guilt/conviction/percentage-chance language is redacted; structured outputs are scanned and the workflow fails validation if triggered), mandatory disclaimer, mock/live/synthetic banners on every report and chat answer.

## Providers (`services/providers.py`)
`LLM`, `Embedder`, OCR, STT, TTS, avatar, `Storage` are interfaces selected by env vars. Mocks are deterministic and labelled. OpenAI/Gemini LLM + embedding adapters and an S3 storage adapter are implemented but **untested** (no keys). STT/TTS/avatar live vendors are intentionally left as stubs behind the same interface.
