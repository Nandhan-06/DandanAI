"""Virtual end-to-end smoke test over REAL HTTP against a running backend (+ optional frontend).
Usage: python scripts/e2e_smoke.py http://127.0.0.1:8000 [http://127.0.0.1:3000]
Backend must run with APP_ENV=test ALLOW_EPHEMERAL_TEST_DB=true (see scripts/virtual_e2e.sh). Never touches Neon."""
import io
import sys
import time

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
WEB = sys.argv[2] if len(sys.argv) > 2 else None
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASSED " if cond else "FAILED ") + name + (f"  [{extra}]" if extra and not cond else ""))


c = httpx.Client(base_url=API, timeout=60)
st = c.get("/api/v1/system/status").json()
check("backend reachable; mock mode + non-Neon test DB reported honestly", st["mode"]["overall"] == "mock" and st["database"]["state"] == "EPHEMERAL_TEST_DB_NOT_NEON")
pw = "E2eSecret12345"
a = c.post("/api/v1/auth/register", json={"email": "e2e.a@example.com", "password": pw, "full_name": "E2E Advocate A"}).json()
b = c.post("/api/v1/auth/register", json={"email": "e2e.b@example.com", "password": pw, "full_name": "E2E Advocate B"}).json()
ha, hb = {"Authorization": "Bearer " + a["access_token"]}, {"Authorization": "Bearer " + b["access_token"]}
case = c.post("/api/v1/cases", json={"title": "E2E tenancy", "case_type": "tenancy", "jurisdiction": "India"}, headers=ha).json()
cid = case["id"]
check("case created", "id" in case)
import pymupdf
d = pymupdf.open(); p = d.new_page()
p.insert_textbox(pymupdf.Rect(40, 40, 550, 800), 'RENTAL AGREEMENT dated 12 March 2024 between Mr. Ravi Kumar (the "Landlord") and Ms. Anita Rao (the "Tenant").\n1. Rent: The monthly rent shall be Rs. 25,000.\n2. Termination: Either party may terminate with 30 days notice. Tenancy for a period of 11 months.', fontsize=10)
up = c.post(f"/api/v1/cases/{cid}/documents", files={"file": ("rent.pdf", d.tobytes(), "application/pdf")}, headers=ha)
check("document upload accepted", up.status_code == 201)
for _ in range(40):
    doc = c.get(f"/api/v1/cases/{cid}/documents/{up.json()['id']}", headers=ha).json()
    if doc["processing_status"] not in ("uploaded", "processing"):
        break
    time.sleep(0.25)
check("document extracted + classified", doc["processing_status"] == "extracted" and doc["doc_type"] == "rental_agreement")
c.post(f"/api/v1/cases/{cid}/issues", json={"title": "Security deposit refund"}, headers=ha)
run = c.post(f"/api/v1/cases/{cid}/workflows/assessment", json={"client_side": "tenant"}, headers=ha).json()
check("LangGraph assessment reaches human-review gate", run["status"] == "awaiting_review")
check("tenant isolation: B cannot read A's case/run/report", c.get(f"/api/v1/cases/{cid}", headers=hb).status_code == 404 and c.get(f"/api/v1/workflows/{run['id']}", headers=hb).status_code == 404 and c.get(f"/api/v1/reports/{run['report_id']}", headers=hb).status_code == 404)
ap = c.post(f"/api/v1/workflows/{run['id']}/approve", json={"note": "e2e"}, headers=ha)
check("advocate approves report", ap.status_code == 200 and ap.json()["report"]["status"] == "approved")
pdf = c.get(f"/api/v1/reports/{run['report_id']}/export?format=pdf", headers=ha)
check("PDF export", pdf.content[:4] == b"%PDF")
cr = c.post(f"/api/v1/cases/{cid}/workflows/criminal", json={"incident": "On 3 May 2024 an unknown person snatched my phone worth Rs. 9,000 without my consent near the bus stand.", "perspective": "defence"}, headers=ha).json()
check("DandanAI workflow completes", cr["status"] == "awaiting_review")
check("logout invalidates token", c.post("/api/v1/auth/logout", headers=ha).status_code == 204 and c.get("/api/v1/auth/me", headers=ha).status_code == 401)
pre = c.options("/api/v1/cases", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
check("CORS preflight allows the frontend origin", pre.headers.get("access-control-allow-origin") == "http://localhost:3000")
if WEB:
    w = httpx.Client(base_url=WEB, timeout=30)
    for path in ("/login", "/register", "/", "/cases", "/documents", "/research", "/chat", "/workflows", "/criminal", "/sources", "/admin", "/settings"):
        r = w.get(path)
        check(f"frontend serves {path}", r.status_code == 200 and "DandanAI" in r.text or r.status_code == 200)
bad = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(bad)}/{len(results)} passed")
sys.exit(1 if bad else 0)
