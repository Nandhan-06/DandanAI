import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models import Case, CaseMember, User

bearer = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    unauth = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauth
    payload = decode_access_token(creds.credentials)
    if not payload:
        raise unauth
    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (ValueError, KeyError):
        raise unauth
    # identity always comes from the server-side record; token_version mismatch == logged out / revoked
    if not user or not user.is_active or user.token_version != payload.get("ver"):
        raise unauth
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user
    return checker


def case_access(db: Session, user: User, case_id: uuid.UUID) -> tuple[Case, str]:
    """Backend-level case authorisation. Returns (case, level) where level in owner|editor|viewer.

    Org + owner/member checks happen here for EVERY case-scoped route. Admins manage users but get no
    case-content access. Non-authorised callers receive 404 so existence is never leaked."""
    case = db.get(Case, case_id)
    nf = HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    if not case or case.org_id != user.org_id or user.role == "admin":
        raise nf
    if case.owner_id == user.id:
        return case, "owner"
    m = db.scalar(select(CaseMember).where(CaseMember.case_id == case.id, CaseMember.user_id == user.id))
    if not m:
        raise nf
    return case, m.access


def accessible_case_ids(db: Session, user: User) -> list[uuid.UUID]:
    if user.role == "admin":
        return []
    own = db.scalars(select(Case.id).where(Case.owner_id == user.id, Case.org_id == user.org_id)).all()
    shared = db.scalars(select(CaseMember.case_id).join(Case, Case.id == CaseMember.case_id)
                        .where(CaseMember.user_id == user.id, Case.org_id == user.org_id)).all()
    return list({*own, *shared})


class CaseCtx:
    def __init__(self, case: Case, level: str, user: User):
        self.case, self.level, self.user = case, level, user


def get_case_read(case_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CaseCtx:
    c, lvl = case_access(db, user, case_id)
    return CaseCtx(c, lvl, user)


def get_case_write(case_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CaseCtx:
    c, lvl = case_access(db, user, case_id)
    if lvl == "viewer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Read-only access to this case")
    return CaseCtx(c, lvl, user)


def get_case_advocate(case_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CaseCtx:
    """Consequential actions (assessments, approvals) need an advocate with case access."""
    c, lvl = case_access(db, user, case_id)
    if user.role != "advocate" or lvl == "viewer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an advocate with write access may do this")
    return CaseCtx(c, lvl, user)
