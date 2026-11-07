import time

from tests.conftest import RENT_A, RENT_B, make_docx, make_pdf, make_png


def test_case_crud_and_children(client, world, case_a):
    h, cid = world["a"], case_a["id"]
    assert client.patch(f"/api/v1/cases/{cid}", json={"forum": "Rent Court"}, headers=h).json()["forum"] == "Rent Court"
    p = client.post(f"/api/v1/cases/{cid}/parties", json={"name": "Anita Rao", "role": "tenant"}, headers=h)
    f = client.post(f"/api/v1/cases/{cid}/facts", json={"text": "Deposit not returned", "disputed": True, "fact_date": "2024-05-01"}, headers=h)
    i = client.post(f"/api/v1/cases/{cid}/issues", json={"title": "Security deposit refund"}, headers=h).json()
    e = client.post(f"/api/v1/cases/{cid}/evidence", json={"title": "Bank transfer receipt", "issue_ids": [i["id"]]}, headers=h)
    t = client.post(f"/api/v1/cases/{cid}/tasks", json={"title": "File reply", "kind": "deadline", "due_date": "2020-01-01"}, headers=h)
    assert all(x.status_code == 201 for x in (p, f, e, t))
    assert client.patch(f"/api/v1/cases/{cid}/tasks/{t.json()['id']}", json={"due_date": "2020-02-02"}, headers=h).status_code == 200
    m = client.get(f"/api/v1/cases/{cid}/evidence-matrix", headers=h).json()
    assert m["rows"][0]["cells"][i["id"]] == "supports"
    ck = client.get(f"/api/v1/cases/{cid}/cockpit", headers=h).json()
    assert any(a["flag"] == "overdue" for a in ck["alerts"])
    tw = client.post(f"/api/v1/cases/{cid}/twin/rebuild", headers=h).json()
    assert tw["version"] >= 1 and tw["data"]["parties"][0]["name"] == "Anita Rao"
    assert client.get("/api/v1/cases?q=Tenancy", headers=h).json()
    assert client.post(f"/api/v1/cases/{cid}/archive", headers=h).json()["status"] == "archived"


def test_tenant_isolation_everywhere(client, world, case_a):
    cid, hb = case_a["id"], world["b"]
    client.post(f"/api/v1/cases/{cid}/documents", files={"file": ("a.pdf", make_pdf(RENT_A), "application/pdf")}, data={"doc_type": "auto"}, headers=world["a"])
    assert client.get("/api/v1/cases", headers=hb).json() == [] or all(c["id"] != cid for c in client.get("/api/v1/cases", headers=hb).json())
    for path in ("", "/documents", "/parties", "/evidence-matrix", "/cockpit", "/twin", "/members", "/activity"):
        assert client.get(f"/api/v1/cases/{cid}{path}", headers=hb).status_code == 404, path
    assert client.patch(f"/api/v1/cases/{cid}", json={"title": "pwn"}, headers=hb).status_code == 404
    assert client.post(f"/api/v1/cases/{cid}/documents", files={"file": ("a.pdf", make_pdf("x"), "application/pdf")}, headers=hb).status_code == 404
    assert client.post(f"/api/v1/cases/{cid}/workflows/assessment", json={}, headers=hb).status_code == 404
    # admin gets no case content either
    assert client.get(f"/api/v1/cases/{cid}", headers=world["admin"]).status_code == 404
    # same-org colleague without explicit share is also blocked
    assert client.get(f"/api/v1/cases/{cid}", headers=world["peer"]).status_code == 404
    # retrieval over case documents is tenant-scoped (embeddings/chunks)
    from app.database import session_factory
    from app.models import User
    from app.services.rag import search_case_docs
    from app.deps import accessible_case_ids
    from sqlalchemy import select
    db = session_factory()()
    ub = db.scalar(select(User).where(User.email == "adv.b@test.example"))
    assert search_case_docs(db, "security deposit rent", accessible_case_ids(db, ub), ub.org_id) == []
    db.close()


def test_sharing_and_assistant_permissions(client, world, case_a):
    cid = case_a["id"]
    assert client.get(f"/api/v1/cases/{cid}", headers=world["asst"]).status_code == 404
    r = client.post(f"/api/v1/cases/{cid}/members", json={"user_email": "assistant@test.example", "access": "editor"}, headers=world["a"])
    assert r.status_code == 201
    assert client.get(f"/api/v1/cases/{cid}", headers=world["asst"]).status_code == 200
    assert client.post(f"/api/v1/cases/{cid}/facts", json={"text": "assistant fact"}, headers=world["asst"]).status_code == 201
    # assistants cannot run consequential workflows
    assert client.post(f"/api/v1/cases/{cid}/workflows/assessment", json={}, headers=world["asst"]).status_code == 403
    # cross-org sharing refused
    assert client.post(f"/api/v1/cases/{cid}/members", json={"user_email": "adv.b@test.example"}, headers=world["a"]).status_code == 404
    client.post(f"/api/v1/cases/{cid}/members", json={"user_email": "peer.a2@test.example", "access": "viewer"}, headers=world["a"])
    assert client.post(f"/api/v1/cases/{cid}/facts", json={"text": "x"}, headers=world["peer"]).status_code == 403


def _wait(client, cid, did, h):
    for _ in range(30):
        d = client.get(f"/api/v1/cases/{cid}/documents/{did}", headers=h).json()
        if d["processing_status"] not in ("uploaded", "processing"):
            return d
        time.sleep(0.1)
    return d


def test_upload_extraction_provenance_and_validation(client, world, case_a):
    h, cid = world["a"], case_a["id"]
    r = client.post(f"/api/v1/cases/{cid}/documents", files={"file": ("rent.pdf", make_pdf(RENT_A), "application/pdf")}, headers=h)
    assert r.status_code == 201
    d = _wait(client, cid, r.json()["id"], h)
    assert d["processing_status"] == "extracted" and d["doc_type"] == "rental_agreement"
    ex = client.get(f"/api/v1/cases/{cid}/documents/{d['id']}/extractions", headers=h).json()
    kinds = {e["kind"] for e in ex}
    assert {"party", "date", "amount", "clause", "duration"} <= kinds
    assert all(e["page"] == 1 for e in ex if e["origin"] == "explicit")  # page provenance
    assert any(e["kind"] == "amount" and "25,000" in e["value"] for e in ex)
    rv = client.patch(f"/api/v1/cases/{cid}/documents/{d['id']}/extractions/{ex[0]['id']}", json={"review_status": "edited", "edited_value": "fixed"}, headers=h)
    assert rv.json()["edited_value"] == "fixed"
    # docx, version, compare
    r2 = client.post(f"/api/v1/cases/{cid}/documents", files={"file": ("rent2.docx", make_docx(RENT_B), "application/octet-stream")}, data={"replaces_document_id": d["id"]}, headers=h)
    d2 = _wait(client, cid, r2.json()["id"], h)
    assert d2["processing_status"] == "extracted" and d2["version"] == 2
    cmp = client.post(f"/api/v1/cases/{cid}/documents/compare", json={"document_a": d["id"], "document_b": d2["id"]}, headers=h).json()
    assert cmp["clause_differences"] and cmp["financial_terms"]["only_in_b"]
    # image: mock OCR is flagged, never passed off as content
    r3 = client.post(f"/api/v1/cases/{cid}/documents", files={"file": ("scan.png", make_png(), "image/png")}, headers=h)
    d3 = _wait(client, cid, r3.json()["id"], h)
    assert d3["processing_status"] in ("extracted_mock_ocr", "needs_ocr")
    # rejections
    assert client.post(f"/api/v1/cases/{cid}/documents", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, headers=h).status_code == 415
    assert client.post(f"/api/v1/cases/{cid}/documents", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")}, headers=h).status_code == 415
    assert client.post(f"/api/v1/cases/{cid}/documents", files={"file": ("a.pdf", make_pdf("x"), "application/pdf")}, data={"doc_type": "bogus"}, headers=h).status_code == 422
    assert client.get(f"/api/v1/cases/{cid}/documents/{d['id']}/download", headers=h).content[:5] == b"%PDF-"
