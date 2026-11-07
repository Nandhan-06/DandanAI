import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.util import to_dict
from app.core.security import hash_password, password_problem
from app.database import get_db
from app.deps import require_roles
from app.models import AuditLog, Case, Document, Organisation, User, WorkflowRun
from app.services.audit import audit

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
admin_only = require_roles("admin")


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(min_length=2)
    role: str = "advocate"


class UserPatch(BaseModel):
    role: str | None = None
    is_active: bool | None = None


@router.get("/users")
def list_users(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [to_dict(u) for u in db.scalars(select(User).where(User.org_id == admin.org_id).order_by(User.created_at)).all()]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    if body.role not in ("admin", "advocate", "legal_assistant"):
        raise HTTPException(422, "Invalid role")
    if (p := password_problem(body.password)):
        raise HTTPException(422, p)
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Email already registered")
    u = User(org_id=admin.org_id, email=body.email.lower(), password_hash=hash_password(body.password), full_name=body.full_name, role=body.role)
    db.add(u)
    db.flush()
    audit(db, admin, "admin.user_create", "user", u.id, {"role": body.role})
    db.commit()
    return to_dict(u)


@router.patch("/users/{user_id}")
def patch_user(user_id: uuid.UUID, body: UserPatch, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.org_id != admin.org_id:
        raise HTTPException(404, "User not found")
    if u.id == admin.id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(422, "Admins cannot demote or deactivate themselves")
    if body.role:
        if body.role not in ("admin", "advocate", "legal_assistant"):
            raise HTTPException(422, "Invalid role")
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    u.token_version += 1  # force re-login after permission change
    audit(db, admin, "admin.user_update", "user", u.id, body.model_dump(exclude_none=True))
    db.commit()
    return to_dict(u)


@router.get("/audit")
def audit_logs(limit: int = 100, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.org_id == admin.org_id).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()
    return [to_dict(r) for r in rows]


@router.get("/stats")
def stats(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    org = db.get(Organisation, admin.org_id)
    c = lambda m: db.scalar(select(func.count()).select_from(m).where(m.org_id == admin.org_id))  # noqa: E731
    return {"organisation": {"name": org.name, "code": org.code}, "users": c(User), "cases": c(Case), "documents": c(Document), "workflow_runs": c(WorkflowRun),
            "note": "Admins see counts and users only; case content is not accessible to admin accounts."}
