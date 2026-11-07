"""Structured local logs; optional Langfuse adapter activates only when keys are configured."""
import json
import logging
import time

from app.core.config import get_settings

log = logging.getLogger("dandanai")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

_lf = None


def _langfuse():
    global _lf
    s = get_settings()
    if _lf is None and s.langfuse_public_key and s.langfuse_secret_key:
        try:
            from langfuse import Langfuse  # optional dependency
            _lf = Langfuse(public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key, host=s.langfuse_host or None)
        except Exception:  # noqa: BLE001
            _lf = False
    return _lf or None


def trace_event(name: str, data: dict) -> None:
    log.info(json.dumps({"ts": round(time.time(), 3), "event": name, **data}, default=str))
    lf = _langfuse()
    if lf:
        try:
            lf.trace(name=name, metadata=data)
        except Exception:  # noqa: BLE001
            pass


def status() -> dict:
    s = get_settings()
    return {"local_structured_logs": True, "langfuse": "configured" if (s.langfuse_public_key and s.langfuse_secret_key) else "not_configured"}
