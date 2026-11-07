import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_problem(pw: str) -> str | None:
    if len(pw) < 10:
        return "Password must be at least 10 characters"
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must contain letters and digits"
    return None


def _secret_key() -> str:
    s = get_settings()
    return (s.jwt_secret_key.strip() if s.jwt_secret_key and s.jwt_secret_key.strip()
            else "dandanai-secure-jwt-default-fallback-key-32chars-min")


def create_access_token(user_id: uuid.UUID, token_version: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "ver": token_version, "jti": uuid.uuid4().hex,
               "iat": now, "exp": now + timedelta(minutes=s.access_token_minutes)}
    return jwt.encode(payload, _secret_key(), algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    s = get_settings()
    try:
        return jwt.decode(token, _secret_key(), algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None


# naive in-process login throttle (per email). Use a shared store (Redis) when scaling out.
_FAILS: dict[str, list[float]] = {}


def throttled(key: str, limit: int = 8, window: int = 900) -> bool:
    now = time.time()
    _FAILS[key] = [t for t in _FAILS.get(key, []) if now - t < window]
    return len(_FAILS[key]) >= limit


def record_failure(key: str) -> None:
    _FAILS.setdefault(key, []).append(time.time())


def clear_failures(key: str) -> None:
    _FAILS.pop(key, None)
