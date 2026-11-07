import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (clear_failures, create_access_token, hash_password, password_problem, record_failure, throttled, verify_password)
from app.database import get_db
from app.deps import get_current_user
from app.models import Organisation, User
from app.services.audit import audit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_DUMMY = hash_password("dummy-password-for-timing-1")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    full_name: str = Field(min_length=2, max_length=200)
    role: str = "advocate"  # advocate | legal_assistant ONLY (admin can never self-register)
    organisation_code: str | None = None
    organisation_name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def user_out(u: User) -> dict:
    return {"id": str(u.id), "email": u.email, "full_name": u.full_name, "role": u.role, "org_id": str(u.org_id), "bar_council_id": u.bar_council_id,
            "preferences": u.preferences or {}}


def new_org_code() -> str:
    return "ORG-" + secrets.token_hex(4).upper()


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if body.role not in ("advocate", "legal_assistant"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This role cannot be self-registered")
    if (p := password_problem(body.password)):
        raise HTTPException(422, p)
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    if body.organisation_code:
        org = db.scalar(select(Organisation).where(Organisation.code == body.organisation_code.strip().upper()))
        if not org:
            raise HTTPException(404, "Unknown organisation code")
    else:
        org = Organisation(name=body.organisation_name or f"{body.full_name}'s chambers", code=new_org_code())
        db.add(org)
        db.flush()
    u = User(org_id=org.id, email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip(), role=body.role)
    db.add(u)
    db.flush()
    audit(db, u, "auth.register", "user", u.id, {"role": u.role})
    db.commit()
    return {"user": user_out(u), "access_token": create_access_token(u.id, u.token_version), "token_type": "bearer", "organisation_code": org.code}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if throttled(email):
        raise HTTPException(429, "Too many failed attempts. Try again later.")
    u = db.scalar(select(User).where(User.email == email))
    ok = verify_password(body.password, u.password_hash if u else _DUMMY)  # constant-ish time for unknown users
    if not u or not ok or not u.is_active:
        record_failure(email)
        audit(db, None, "auth.login_failed", "user", None, {"email": email})
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    clear_failures(email)
    audit(db, u, "auth.login", "user", u.id)
    db.commit()
    return {"access_token": create_access_token(u.id, u.token_version), "token_type": "bearer", "user": user_out(u)}


@router.post("/logout", status_code=204)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.token_version += 1  # invalidates every previously issued token
    audit(db, user, "auth.logout", "user", user.id)
    db.commit()


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = db.get(Organisation, user.org_id)
    return {**user_out(user), "organisation": {"name": org.name, "code": org.code if user.role in ("admin", "advocate") else None}}


class ProfileIn(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    bar_council_id: str | None = Field(None, max_length=64)
    preferences: dict | None = None
    current_password: str | None = None
    new_password: str | None = None


@router.patch("/me")
def update_me(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.full_name:
        user.full_name = body.full_name.strip()
    if body.bar_council_id is not None:
        user.bar_council_id = body.bar_council_id
    if body.preferences is not None:
        if len(str(body.preferences)) > 4000:
            raise HTTPException(422, "preferences too large")
        user.preferences = body.preferences
    if body.new_password:
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(403, "Current password incorrect")
        if (p := password_problem(body.new_password)):
            raise HTTPException(422, p)
        user.password_hash = hash_password(body.new_password)
        user.token_version += 1
    audit(db, user, "auth.profile_update", "user", user.id)
    db.commit()
    return user_out(user)
