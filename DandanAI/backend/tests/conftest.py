import io
import os
import tempfile

# Automated tests use an explicit, ephemeral, NON-Neon database (see app/database.py). Never enabled outside APP_ENV=test.
os.environ.update({"APP_ENV": "test", "ALLOW_EPHEMERAL_TEST_DB": "true", "DATABASE_URL": "", "DIRECT_URL": "", "STORAGE_DIR": tempfile.mkdtemp(),
                   "JWT_SECRET_KEY": "test-secret-key-test-secret-key-1234", "BOOTSTRAP_ADMIN_EMAIL": "admin@test.example",
                   "BOOTSTRAP_ADMIN_PASSWORD": "AdminPass12345", "LLM_PROVIDER": "mock", "EMBEDDING_PROVIDER": "mock", "OCR_PROVIDER": "mock"})
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PW = "SecretPass123"


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def _reg(client, email, role="advocate", code=None, name="Test User"):
    body = {"email": email, "password": PW, "full_name": name, "role": role}
    if code:
        body["organisation_code"] = code
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def world(client):
    """Synthetic users: Admin, Advocate A (+ Legal Assistant in A's org), Advocate B (separate org)."""
    adm = client.post("/api/v1/auth/login", json={"email": "admin@test.example", "password": "AdminPass12345"}).json()
    a = _reg(client, "adv.a@test.example", name="Advocate A")
    b = _reg(client, "adv.b@test.example", name="Advocate B")
    asst = _reg(client, "assistant@test.example", role="legal_assistant", code=a["organisation_code"], name="Assistant")
    peer = _reg(client, "peer.a2@test.example", code=a["organisation_code"], name="Advocate A2 (same org)")
    return {"admin": hdr(adm["access_token"]), "a": hdr(a["access_token"]), "b": hdr(b["access_token"]), "asst": hdr(asst["access_token"]),
            "peer": hdr(peer["access_token"]), "a_user": a["user"], "asst_user": asst["user"], "org_code": a["organisation_code"]}


def make_pdf(text: str) -> bytes:
    import pymupdf
    d = pymupdf.open()
    for chunk in text.split("\f"):
        p = d.new_page()
        p.insert_textbox(pymupdf.Rect(40, 40, 550, 800), chunk, fontsize=10)
    return d.tobytes()


def make_docx(text: str) -> bytes:
    import docx
    d = docx.Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def make_png() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(b, "PNG")
    return b.getvalue()


RENT_A = """RENTAL AGREEMENT
This agreement dated 12 March 2024 is made between Mr. Ravi Kumar (the "Landlord") and Ms. Anita Rao (the "Tenant").
1. Rent: The monthly rent shall be Rs. 25,000 payable on or before the 5th of every month.
2. Security Deposit: The Tenant shall pay Rs. 75,000 as refundable deposit.
3. Termination: Either party may terminate with 30 days notice.
The tenancy is for a period of 11 months. Governing law: courts at Bengaluru have jurisdiction. Signed by both parties in witness whereof."""
RENT_B = RENT_A.replace("Rs. 25,000", "Rs. 30,000").replace("30 days notice", "60 days notice").replace("11 months", "12 months")


@pytest.fixture
def case_a(client, world):
    r = client.post("/api/v1/cases", json={"title": "Tenancy dispute A", "case_type": "tenancy", "jurisdiction": "India", "description": "Security deposit not refunded"}, headers=world["a"])
    assert r.status_code == 201
    return r.json()
