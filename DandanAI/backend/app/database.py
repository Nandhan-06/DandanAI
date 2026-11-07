"""Neon-only database access.

* DATABASE_URL (pooled) serves application traffic; DIRECT_URL is for Alembic.
* No silent fallback exists. If Neon is not configured the API answers 503 on DB routes and
  /api/v1/system/status reports `database.state = "BLOCKED_NO_NEON_CREDENTIALS"`.
* The ONLY exception is an explicit, loudly-labelled ephemeral SQLite used by the automated tests
  (requires APP_ENV=test AND ALLOW_EPHEMERAL_TEST_DB=true). It is never enabled by default.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


class DatabaseNotConfigured(RuntimeError):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None
_mode = "unconfigured"  # neon | ephemeral_test | unconfigured


def normalize_pg_url(url: str, *, require_ssl: bool = True) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if not url.startswith("postgresql+psycopg://"):
        raise DatabaseNotConfigured("DATABASE_URL must be a Neon PostgreSQL URL (postgresql://...)")
    p = urlparse(url)
    q = dict(parse_qsl(p.query))
    if require_ssl and "sslmode" not in q and p.hostname not in ("localhost", "127.0.0.1"):
        q["sslmode"] = "require"
    return urlunparse(p._replace(query=urlencode(q)))


def init_engine(force: bool = False):
    global _engine, _SessionLocal, _mode
    if _engine is not None and not force:
        return _engine
    s = get_settings()
    if s.app_env == "test" and s.allow_ephemeral_test_db and not s.database_url:
        _engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        _mode = "ephemeral_test"
    elif s.database_url:
        url = normalize_pg_url(s.database_url)
        # prepare_threshold=None keeps psycopg3 compatible with Neon's PgBouncer (transaction pooling)
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=300,
                                connect_args={"prepare_threshold": None})
        _mode = "neon"
    else:
        raise DatabaseNotConfigured("DATABASE_URL is not set. Add your Neon pooled connection string to .env")
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def reset_engine():
    global _engine, _SessionLocal, _mode
    if _engine is not None:
        _engine.dispose()
    _engine, _SessionLocal, _mode = None, None, "unconfigured"


def session_factory() -> sessionmaker:
    init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db():
    try:
        factory = session_factory()
    except DatabaseNotConfigured as e:
        raise HTTPException(503, f"Database unavailable: {e}")
    db: Session = factory()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create schema. Production path = `alembic upgrade head`; this helper is for the ephemeral test DB only."""
    from app import models  # noqa: F401

    eng = init_engine()
    if _mode == "neon":
        raise RuntimeError("Use `alembic upgrade head` (DIRECT_URL) to create the Neon schema")
    Base.metadata.create_all(eng)


def db_state() -> dict:
    s = get_settings()
    if not s.database_url and not (s.app_env == "test" and s.allow_ephemeral_test_db):
        return {"state": "BLOCKED_NO_NEON_CREDENTIALS", "provider": "neon", "verified": False,
                "detail": "Set DATABASE_URL and DIRECT_URL in .env, then run `alembic upgrade head`."}
    try:
        eng = init_engine()
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        if _mode == "ephemeral_test":
            return {"state": "EPHEMERAL_TEST_DB_NOT_NEON", "provider": "sqlite-memory", "verified": False,
                    "detail": "Automated-test database only. NOT Neon."}
        return {"state": "CONNECTED", "provider": "neon", "verified": True, "detail": "SELECT 1 succeeded"}
    except Exception as e:  # noqa: BLE001
        return {"state": "ERROR", "provider": "neon", "verified": False, "detail": type(e).__name__}
