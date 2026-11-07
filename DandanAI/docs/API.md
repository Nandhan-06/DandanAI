# DandanAI — API reference

Interactive docs: `http://localhost:8000/docs` (disabled when `APP_ENV=production`). All routes except `/health`, `/api/v1/system/status`, `/api/v1/auth/register` and `/api/v1/auth/login` require `Authorization: Bearer <JWT>`.
Case-scoped routes enforce owner/shared-member access server-side and return `404` (not `403`) to outsiders. Admin accounts never get case content.

**88 operations**

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/admin/audit` | Audit Logs |
| GET | `/api/v1/admin/stats` | Stats |
| GET | `/api/v1/admin/users` | List Users |
| POST | `/api/v1/admin/users` | Create User |
| PATCH | `/api/v1/admin/users/{user_id}` | Patch User |
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/logout` | Logout |
| GET | `/api/v1/auth/me` | Me |
| PATCH | `/api/v1/auth/me` | Update Me |
| POST | `/api/v1/auth/register` | Register |
| POST | `/api/v1/cases` | Create Case |
| GET | `/api/v1/cases` | List Cases |
| GET | `/api/v1/cases/{case_id}` | Get Case |
| PATCH | `/api/v1/cases/{case_id}` | Patch Case |
| GET | `/api/v1/cases/{case_id}/activity` | Activity |
| POST | `/api/v1/cases/{case_id}/archive` | Archive |
| GET | `/api/v1/cases/{case_id}/cockpit` | Cockpit |
| POST | `/api/v1/cases/{case_id}/documents` | Upload |
| GET | `/api/v1/cases/{case_id}/documents` | List Docs |
| POST | `/api/v1/cases/{case_id}/documents/compare` | Compare |
| GET | `/api/v1/cases/{case_id}/documents/{document_id}` | Get Doc |
| GET | `/api/v1/cases/{case_id}/documents/{document_id}/download` | Download |
| GET | `/api/v1/cases/{case_id}/documents/{document_id}/extractions` | Extractions |
| PATCH | `/api/v1/cases/{case_id}/documents/{document_id}/extractions/{extraction_id}` | Review Extraction |
| POST | `/api/v1/cases/{case_id}/documents/{document_id}/reprocess` | Reprocess |
| GET | `/api/v1/cases/{case_id}/documents/{document_id}/text` | Text |
| GET | `/api/v1/cases/{case_id}/documents/{document_id}/versions` | Versions |
| GET | `/api/v1/cases/{case_id}/evidence` | List Evidence |
| POST | `/api/v1/cases/{case_id}/evidence` | Create Evidence |
| GET | `/api/v1/cases/{case_id}/evidence-matrix` | Evidence Matrix |
| PATCH | `/api/v1/cases/{case_id}/evidence/{item_id}` | Update Evidence |
| DELETE | `/api/v1/cases/{case_id}/evidence/{item_id}` | Delete Evidence |
| GET | `/api/v1/cases/{case_id}/facts` | List Facts |
| POST | `/api/v1/cases/{case_id}/facts` | Create Facts |
| PATCH | `/api/v1/cases/{case_id}/facts/{item_id}` | Update Facts |
| DELETE | `/api/v1/cases/{case_id}/facts/{item_id}` | Delete Facts |
| GET | `/api/v1/cases/{case_id}/issues` | List Issues |
| POST | `/api/v1/cases/{case_id}/issues` | Create Issues |
| PATCH | `/api/v1/cases/{case_id}/issues/{item_id}` | Update Issues |
| DELETE | `/api/v1/cases/{case_id}/issues/{item_id}` | Delete Issues |
| POST | `/api/v1/cases/{case_id}/members` | Share |
| GET | `/api/v1/cases/{case_id}/members` | Members |
| DELETE | `/api/v1/cases/{case_id}/members/{user_id}` | Unshare |
| GET | `/api/v1/cases/{case_id}/parties` | List Parties |
| POST | `/api/v1/cases/{case_id}/parties` | Create Parties |
| PATCH | `/api/v1/cases/{case_id}/parties/{item_id}` | Update Parties |
| DELETE | `/api/v1/cases/{case_id}/parties/{item_id}` | Delete Parties |
| GET | `/api/v1/cases/{case_id}/tasks` | List Tasks |
| POST | `/api/v1/cases/{case_id}/tasks` | Create Tasks |
| PATCH | `/api/v1/cases/{case_id}/tasks/{item_id}` | Update Tasks |
| DELETE | `/api/v1/cases/{case_id}/tasks/{item_id}` | Delete Tasks |
| GET | `/api/v1/cases/{case_id}/timeline` | List Timeline |
| POST | `/api/v1/cases/{case_id}/timeline` | Create Timeline |
| PATCH | `/api/v1/cases/{case_id}/timeline/{item_id}` | Update Timeline |
| DELETE | `/api/v1/cases/{case_id}/timeline/{item_id}` | Delete Timeline |
| GET | `/api/v1/cases/{case_id}/twin` | Twin |
| POST | `/api/v1/cases/{case_id}/twin/rebuild` | Rebuild Twin |
| POST | `/api/v1/cases/{case_id}/workflows/assessment` | Run Assessment |
| POST | `/api/v1/cases/{case_id}/workflows/criminal` | Run Criminal |
| GET | `/api/v1/chat/conversations` | Convs |
| POST | `/api/v1/chat/conversations` | New Conv |
| GET | `/api/v1/chat/conversations/{cid}/messages` | Msgs |
| POST | `/api/v1/chat/conversations/{cid}/messages` | Send |
| GET | `/api/v1/coverage` | Coverage |
| GET | `/api/v1/ingestion-jobs` | Jobs |
| GET | `/api/v1/instruments` | Instruments |
| POST | `/api/v1/instruments/ingest` | Ingest |
| GET | `/api/v1/instruments/{iid}` | Instrument |
| POST | `/api/v1/instruments/{iid}/amendments` | Add Amendment |
| POST | `/api/v1/instruments/{iid}/verify` | Verify Instrument |
| GET | `/api/v1/reports` | List Reports |
| GET | `/api/v1/reports/{rid}` | Get Report |
| GET | `/api/v1/reports/{rid}/export` | Export |
| POST | `/api/v1/research/search` | Research |
| GET | `/api/v1/sources` | Sources |
| PATCH | `/api/v1/sources/{sid}` | Patch Source |
| POST | `/api/v1/sources/{sid}/check` | Monitor Source |
| GET | `/api/v1/system/status` | Status |
| POST | `/api/v1/voice/avatar` | Avatar |
| POST | `/api/v1/voice/transcribe` | Transcribe |
| POST | `/api/v1/voice/tts` | Tts |
| GET | `/api/v1/workflows` | List Runs |
| GET | `/api/v1/workflows/{run_id}` | Get Run |
| POST | `/api/v1/workflows/{run_id}/approve` | Approve |
| POST | `/api/v1/workflows/{run_id}/reject` | Reject |
| POST | `/api/v1/workflows/{run_id}/resume` | Resume |
| GET | `/api/v1/workflows/{run_id}/state` | Get State |
| GET | `/health` | Health |
