# Requirement traceability matrix

Status legend: **PASSED** = automated test executed successfully here · **IMPLEMENTED (UNTESTED)** = code exists, no executed test · **MOCK** = works only with deterministic mock · **BLOCKED** = needs external credentials · **PARTIAL / NOT BUILT** = see notes.

| # | Requirement (source) | Implementation | Verification | Status |
|---|---|---|---|---|
| 1 | Registration, login/logout, JWT, Argon2 (Capstone §2, Spec A) | `api/auth.py`, `core/security.py` | `test_auth_rbac.py` | PASSED |
| 2 | Roles Admin/Advocate/Legal Assistant; admin never self-registered | `deps.py`, `api/auth.py`, `api/admin.py` | `test_register_rejects_admin…`, `test_admin_rbac` | PASSED |
| 3 | Logout token invalidation | `token_version` | `test_login_logout_invalidates_token` | PASSED |
| 4 | Tenant/case isolation incl. embeddings, reports, runs | `deps.case_access`, org-scoped chunks | `test_tenant_isolation_everywhere`, `test_assessment_workflow…`, E2E | PASSED |
| 5 | Case CRUD, parties, facts, issues, evidence, tasks, timeline, search, archive, activity | `api/cases.py` | `test_case_crud_and_children` | PASSED |
| 6 | Documents PDF/DOCX/PNG/JPG, validation, size/type/magic-byte checks | `api/documents.py`, `services/extraction.py` | `test_upload_extraction…` | PASSED |
| 7 | Scanned documents via OCR | adapter; Tesseract path | mock path tested (flagged, no fake text); Tesseract path not exercised | PARTIAL (OCR engine absent in build env) |
| 8 | Extraction w/ page provenance, classification, parties, dates, deadlines, amounts, clauses, obligations, legal refs, missing info | `services/docintel.py` | `test_upload_extraction…` | PASSED (heuristic; English text) |
| 9 | Summarisation | structured summary + narrative via LLM adapter | structure tested; narrative is MOCK | MOCK |
| 10 | Agreement comparison, versioning, human review | `docintel.compare`, versions, extraction PATCH | `test_upload_extraction…` | PASSED |
| 11 | Source registry, jurisdiction hierarchy (28+8+25 HC), licensing/access status, coverage dashboard, never claims completeness | `services/seed.py`, `api/research.py` | `test_coverage_dashboard_is_honest` | PASSED (registry rows are placeholders) |
| 12 | Instrument versioning, amendments, repeal, temporal filters, human verification, manual ingestion | `api/research.py`, `rag._valid_on` | `test_jurisdiction_and_temporal_filters`, `test_manual_ingestion_versioning`, `test_human_verification…` | PASSED |
| 13 | Automated ingestion from India Code / eCourts etc. | none (monitor hook records manual checks only) | — | NOT BUILT (licence review required first) |
| 14 | Hybrid BM25+vector RAG, pgvector, reranker interface, citations, gaps | `services/rag.py` | `test_research_hybrid_and_gaps` | PASSED (vector math in Python on test DB; pgvector SQL path **not executed**) |
| 15 | Citation verification, fabricated-authority detection | `rag.verify_citation`, `find_uncited_authorities`, agent 5 | `test_citation_verification_detects_fabrication` | PASSED |
| 16 | LangGraph ≥5 agents, typed state, routing, retries, checkpoints, history, human approve/reject | `agents/*`, `services/workflows.py` | `test_assessment_workflow…`, `test_workflow_retry_resume_and_reject` | PASSED |
| 17 | DandanAI: classification, provisions, elements, evidence gaps, similar + contrary judgments, punishment, compensation, report | `agents/criminal.py` | `test_dandan_criminal_engine` | PASSED on SYNTHETIC corpus; real-law accuracy NOT VERIFIED |
| 18 | Never predict guilt / invent probabilities | `guardrails.py` | `test_dandan_guardrail…`, assessment test | PASSED |
| 19 | Case Intelligence Cockpit, Case Twin (versioned), Evidence Matrix, Adverse Precedent Finder, limitation flags | `api/cases.py`, agent 4 | cases + workflow tests | PASSED |
| 20 | Chat, editable voice transcripts, TTS playback, avatar, history | `api/chat.py`, UI `/chat` | `test_chat_and_voice_adapters` (API) | MOCK; browser mic/playback NOT RUN |
| 21 | Reports + PDF/DOCX/MD export (DandanAI §3) | `services/reports.py` | export assertions | PASSED |
| 22 | Guardrails, disclaimer, audit, confidentiality | `guardrails.py`, `audit.py`, security headers | tests above | PASSED |
| 23 | Neon-only DB, pooled/direct URLs, SSL, Alembic, pgvector | `database.py`, `alembic/` | offline SQL generation only | **BLOCKED** live; schema SQL generated, never executed on Postgres |
| 24 | Frontend: all 15 screens, responsive, accessible, real API | `frontend/` | `tsc`, `next build`, HTTP smoke | Builds PASSED; browser interaction NOT RUN |
| 25 | Docker, Compose, CI, Terraform | `docker/`, `.github/`, `infra/` | files written | NOT RUN (no Docker/Terraform in build env) |
| 26 | Quantum-inspired retrieval (DandanAI §5) | — | — | NOT BUILT by design (evidence-first decision in Spec §11; hybrid retrieval used) |
| 27 | Knowledge graph (DandanAI §5) | Case Twin is a structured JSON model; no graph DB | — | PARTIAL |
| 28 | Multilingual support (DandanAI §8) | — | — | NOT BUILT |
| 29 | Langfuse/LangSmith | `services/observability.py` (structured logs always; Langfuse optional) | logs observed | IMPLEMENTED (UNTESTED with Langfuse) |
