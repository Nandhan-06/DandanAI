import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api import admin, auth, cases, chat, documents, research, system, workflows
from app.core.config import get_settings
from app.core.security import hash_password
from app.database import DatabaseNotConfigured, init_db, session_factory
from app.models import Organisation, User
from app.services.seed import seed_sources, seed_synthetic_corpus

log = logging.getLogger("dandanai")


def startup_tasks() -> None:
    s = get_settings()
    try:
        factory = session_factory()
    except DatabaseNotConfigured as e:
        log.warning("DATABASE BLOCKED: %s", e)
        return
    if s.app_env == "test" and s.allow_ephemeral_test_db:
        init_db()
    try:
        db = factory()
        try:
            if s.bootstrap_admin_email and s.bootstrap_admin_password and not db.scalar(select(User).where(User.email == s.bootstrap_admin_email.lower())):
                org = Organisation(name="DandanAI Default Organisation", code="ORG-DEFAULT")
                db.add(org)
                db.flush()
                db.add(User(org_id=org.id, email=s.bootstrap_admin_email.lower(), password_hash=hash_password(s.bootstrap_admin_password), full_name=s.bootstrap_admin_name, role="admin"))
                db.commit()
            seed_sources(db)
            if s.seed_synthetic_corpus:
                seed_synthetic_corpus(db)
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001  (e.g. schema not migrated yet)
        log.warning("Startup seeding skipped: %s: %s (run `alembic upgrade head`)", type(e).__name__, str(e)[:200])


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_tasks()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    if s.is_production and (s.jwt_secret_key.startswith("change-me") or s.jwt_secret_key.startswith("generate-") or len(s.jwt_secret_key) < 32):
        raise RuntimeError("Refusing to start in production: set a strong JWT_SECRET_KEY (>= 32 chars) in .env")
    if s.is_production and s.allow_ephemeral_test_db:
        raise RuntimeError("ALLOW_EPHEMERAL_TEST_DB must never be enabled in production")
    app = FastAPI(title="DandanAI", version="1.0.0", lifespan=lifespan, docs_url=None if s.is_production else "/docs", redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()], allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Voice-Mode", "Content-Disposition"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                             "Cache-Control": "no-store" if request.url.path.startswith("/api/") else resp.headers.get("Cache-Control", "")})
        return resp

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse({"detail": "Internal server error"}, status_code=500)  # no stack traces / internals to clients

    for r in (system.router, auth.router, admin.router, cases.router, documents.router, research.router, workflows.router, workflows.reports, chat.router):
        app.include_router(r)
    return app


app = create_app()
