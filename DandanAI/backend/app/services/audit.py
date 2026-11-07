
from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, user, action: str, resource_type: str | None = None, resource_id=None, detail: dict | None = None,
          org_id=None) -> None:
    """Append an audit record (caller commits). `user` may be a User or None."""
    db.add(AuditLog(user_id=getattr(user, "id", None), org_id=org_id or getattr(user, "org_id", None), action=action,
                    resource_type=resource_type, resource_id=str(resource_id) if resource_id else None, detail=detail))
