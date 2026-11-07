from tests.conftest import PW, hdr


def test_register_rejects_admin_and_weak_password(client):
    r = client.post("/api/v1/auth/register", json={"email": "x@t.example", "password": PW, "full_name": "X Y", "role": "admin"})
    assert r.status_code == 403
    r = client.post("/api/v1/auth/register", json={"email": "x@t.example", "password": "short", "full_name": "X Y"})
    assert r.status_code == 422


def test_login_logout_invalidates_token(client):
    tok = client.post("/api/v1/auth/register", json={"email": "lo@t.example", "password": PW, "full_name": "Lo Gout"}).json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=hdr(tok)).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=hdr(tok)).status_code == 204
    assert client.get("/api/v1/auth/me", headers=hdr(tok)).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "lo@t.example", "password": "wrong-pass-123"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "lo@t.example", "password": PW}).status_code == 200


def test_unauthenticated_and_tampered(client):
    assert client.get("/api/v1/cases").status_code == 401
    assert client.get("/api/v1/cases", headers=hdr("not.a.jwt")).status_code == 401


def test_admin_rbac(client, world):
    assert client.get("/api/v1/admin/users", headers=world["a"]).status_code == 403
    assert client.get("/api/v1/admin/users", headers=world["admin"]).status_code == 200
    r = client.post("/api/v1/admin/users", json={"email": "newadm@t.example", "password": PW, "full_name": "New Admin", "role": "admin"}, headers=world["admin"])
    assert r.status_code == 201
    assert client.post("/api/v1/cases", json={"title": "admin case"}, headers=world["admin"]).status_code == 403
    assert client.get("/api/v1/admin/audit", headers=world["admin"]).json()


def test_argon2_hash_stored(client):
    from app.database import session_factory
    from app.models import User
    from sqlalchemy import select
    db = session_factory()()
    h = db.scalar(select(User.password_hash).where(User.email == "adv.a@test.example"))
    db.close()
    assert h.startswith("$argon2")


def test_production_refuses_weak_secret(monkeypatch):
    import pytest
    from app.core.config import get_settings
    from app.main import create_app
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me-in-env")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        create_app()
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-test-secret-key-1234")
    get_settings.cache_clear()
