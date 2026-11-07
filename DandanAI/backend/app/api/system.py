from fastapi import APIRouter

from app.core.config import get_settings
from app.database import db_state
from app.services import observability, providers
from app.services.guardrails import DISCLAIMER

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}  # liveness only; does not touch the database


@router.get("/api/v1/system/status")
def status():
    s = get_settings()
    return {"app_env": s.app_env, "mode": providers.mode(), "database": db_state(), "storage": s.storage_provider, "observability": observability.status(),
            "disclaimer": DISCLAIMER, "live_neon_verified": db_state()["state"] == "CONNECTED"}
