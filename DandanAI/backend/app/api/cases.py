import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.util import to_dict
from app.database import get_db
from app.deps import CaseCtx, accessible_case_ids, get_case_advocate, get_case_read, get_case_write, get_current_user
from app.models import (AuditLog, Case, CaseMember, CaseTwinVersion, Document, EvidenceItem, Extraction, Fact, LegalIssue, Party, Report, Task,
                        TimelineEvent, User, WorkflowRun)
from app.services.audit import audit

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])


class CaseIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(None, max_length=20000)
    case_type: str | None = Field(None, max_length=100)
    jurisdiction: str | None = Field(None, max_length=200)
    forum: str | None = Field(None, max_length=200)
    is_synthetic: bool = False


class CasePatch(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=300)
    description: str | None = None
    case_type: str | None = None
    jurisdiction: str | None = None
    forum: str | None = None
    status: str | None = None


@router.post("", status_code=201)
def create_case(body: CaseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "admin":
        raise HTTPException(403, "Admins manage users; they do not create cases")
    c = Case(org_id=user.org_id, owner_id=user.id, **body.model_dump())
    db.add(c)
    db.flush()
    audit(db, user, "case.create", "case", c.id)
    db.commit()
    return to_dict(c)


@router.get("")
def list_cases(q: str | None = None, status: str | None = None, case_type: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = accessible_case_ids(db, user)
    stmt = select(Case).where(Case.id.in_(ids)) if ids else select(Case).where(False)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Case.title.ilike(like), Case.description.ilike(like)))
    if status:
        stmt = stmt.where(Case.status == status)
    if case_type:
        stmt = stmt.where(Case.case_type == case_type)
    return [{**to_dict(c), "is_owner": c.owner_id == user.id} for c in db.scalars(stmt.order_by(Case.updated_at.desc())).all()]


@router.get("/{case_id}")
def get_case(ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    c = ctx.case
    counts = {n: db.scalar(select(func.count()).select_from(m).where(m.case_id == c.id)) for n, m in
              [("documents", Document), ("facts", Fact), ("issues", LegalIssue), ("evidence", EvidenceItem), ("parties", Party), ("tasks", Task), ("timeline", TimelineEvent)]}
    return {**to_dict(c), "access": ctx.level, "counts": counts}


@router.patch("/{case_id}")
def patch_case(body: CasePatch, ctx: CaseCtx = Depends(get_case_write), db: Session = Depends(get_db)):
    d = body.model_dump(exclude_none=True)
    if d.get("status") and d["status"] not in ("open", "archived"):
        raise HTTPException(422, "status must be open|archived")
    for k, v in d.items():
        setattr(ctx.case, k, v)
    audit(db, ctx.user, "case.update", "case", ctx.case.id, d)
    db.commit()
    return to_dict(ctx.case)


@router.post("/{case_id}/archive")
def archive(ctx: CaseCtx = Depends(get_case_write), db: Session = Depends(get_db)):
    ctx.case.status = "archived"
    audit(db, ctx.user, "case.archive", "case", ctx.case.id)
    db.commit()
    return to_dict(ctx.case)


# ------------------------------------------------------------------ sharing (same organisation only)
class ShareIn(BaseModel):
    user_email: str
    access: str = "editor"


@router.post("/{case_id}/members", status_code=201)
def share(body: ShareIn, ctx: CaseCtx = Depends(get_case_advocate), db: Session = Depends(get_db)):
    if ctx.level != "owner":
        raise HTTPException(403, "Only the owner can share a case")
    if body.access not in ("viewer", "editor"):
        raise HTTPException(422, "access must be viewer|editor")
    target = db.scalar(select(User).where(User.email == body.user_email.lower(), User.org_id == ctx.user.org_id))
    if not target or target.role == "admin":
        raise HTTPException(404, "User not found in your organisation")
    m = db.scalar(select(CaseMember).where(CaseMember.case_id == ctx.case.id, CaseMember.user_id == target.id)) or CaseMember(case_id=ctx.case.id, user_id=target.id)
    m.access = body.access
    db.add(m)
    audit(db, ctx.user, "case.share", "case", ctx.case.id, {"with": target.email, "access": body.access})
    db.commit()
    return {"user_id": str(target.id), "email": target.email, "access": m.access}


@router.get("/{case_id}/members")
def members(ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    rows = db.execute(select(CaseMember, User).join(User, User.id == CaseMember.user_id).where(CaseMember.case_id == ctx.case.id)).all()
    return [{"user_id": str(u.id), "email": u.email, "full_name": u.full_name, "role": u.role, "access": m.access} for m, u in rows]


@router.delete("/{case_id}/members/{user_id}", status_code=204)
def unshare(user_id: uuid.UUID, ctx: CaseCtx = Depends(get_case_advocate), db: Session = Depends(get_db)):
    if ctx.level != "owner":
        raise HTTPException(403, "Only the owner can change sharing")
    m = db.scalar(select(CaseMember).where(CaseMember.case_id == ctx.case.id, CaseMember.user_id == user_id))
    if m:
        db.delete(m)
        audit(db, ctx.user, "case.unshare", "case", ctx.case.id, {"user_id": str(user_id)})
        db.commit()


# ------------------------------------------------------------------ child collections (generic CRUD)
def _collection(path: str, Model, fields: dict, order=None):
    """Registers GET/POST/PATCH/DELETE for a case child collection with case-level authorisation."""
    In = type(f"{Model.__name__}In", (BaseModel,), {"__annotations__": {k: v[0] for k, v in fields.items()}, **{k: v[1] for k, v in fields.items()}})

    @router.get(f"/{{case_id}}/{path}", name=f"list_{path}")
    def lst(ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
        stmt = select(Model).where(Model.case_id == ctx.case.id)
        stmt = stmt.order_by(order) if order is not None else stmt.order_by(Model.created_at)
        return [to_dict(r) for r in db.scalars(stmt).all()]

    @router.post(f"/{{case_id}}/{path}", status_code=201, name=f"create_{path}")
    def create(body: In, ctx: CaseCtx = Depends(get_case_write), db: Session = Depends(get_db)):  # type: ignore[valid-type]
        r = Model(case_id=ctx.case.id, **body.model_dump())
        db.add(r)
        db.flush()
        audit(db, ctx.user, f"{path}.create", path, r.id, {"case_id": str(ctx.case.id)})
        db.commit()
        return to_dict(r)

    @router.patch(f"/{{case_id}}/{path}/{{item_id}}", name=f"update_{path}")
    def update(item_id: uuid.UUID, body: dict, ctx: CaseCtx = Depends(get_case_write), db: Session = Depends(get_db)):
        r = db.get(Model, item_id)
        if not r or r.case_id != ctx.case.id:
            raise HTTPException(404, "Not found")
        for k, v in body.items():
            if k in fields or k in ("done", "reviewed", "status"):
                if isinstance(v, str) and k.endswith(("_date", "due_date")):
                    try:
                        v = date.fromisoformat(v) if v else None
                    except ValueError:
                        raise HTTPException(422, f"{k} must be YYYY-MM-DD")
                setattr(r, k, v)
        audit(db, ctx.user, f"{path}.update", path, r.id)
        db.commit()
        return to_dict(r)

    @router.delete(f"/{{case_id}}/{path}/{{item_id}}", status_code=204, name=f"delete_{path}")
    def delete(item_id: uuid.UUID, ctx: CaseCtx = Depends(get_case_write), db: Session = Depends(get_db)):
        r = db.get(Model, item_id)
        if not r or r.case_id != ctx.case.id:
            raise HTTPException(404, "Not found")
        db.delete(r)
        audit(db, ctx.user, f"{path}.delete", path, item_id)
        db.commit()


_collection("parties", Party, {"name": (str, Field(min_length=1, max_length=300)), "role": (str, Field(min_length=1, max_length=100)),
                               "relationship_to": (str | None, None), "notes": (str | None, None)})
_collection("facts", Fact, {"text": (str, Field(min_length=1, max_length=5000)), "disputed": (bool, False), "fact_date": (date | None, None),
                            "document_id": (uuid.UUID | None, None), "page": (int | None, None)})
_collection("issues", LegalIssue, {"title": (str, Field(min_length=1, max_length=300)), "description": (str | None, None)})
_collection("evidence", EvidenceItem, {"title": (str, Field(min_length=1, max_length=300)), "kind": (str, "document"), "description": (str | None, None),
                                       "document_id": (uuid.UUID | None, None), "status": (str, "held"), "issue_ids": (list, []), "fact_ids": (list, []),
                                       "supports": (str, "supports")})
_collection("tasks", Task, {"title": (str, Field(min_length=1, max_length=300)), "kind": (str, "task"), "due_date": (date | None, None),
                            "trigger_date": (date | None, None), "period_days": (int | None, None)})
_collection("timeline", TimelineEvent, {"title": (str, Field(min_length=1, max_length=300)), "event_date": (date | None, None), "description": (str | None, None),
                                        "document_id": (uuid.UUID | None, None), "page": (int | None, None)}, order=TimelineEvent.event_date)


# ------------------------------------------------------------------ intelligence views
@router.get("/{case_id}/evidence-matrix")
def evidence_matrix(ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    issues = db.scalars(select(LegalIssue).where(LegalIssue.case_id == ctx.case.id)).all()
    ev = db.scalars(select(EvidenceItem).where(EvidenceItem.case_id == ctx.case.id)).all()
    rows = [{"evidence_id": str(e.id), "title": e.title, "kind": e.kind, "status": e.status, "supports": e.supports,
             "cells": {str(i.id): (e.supports if str(i.id) in (e.issue_ids or []) else None) for i in issues}} for e in ev]
    gaps = [{"issue_id": str(i.id), "issue": i.title} for i in issues if not any(str(i.id) in (e.issue_ids or []) for e in ev)]
    return {"issues": [{"id": str(i.id), "title": i.title} for i in issues], "rows": rows, "issues_without_evidence": gaps,
            "missing_evidence": [e.title for e in ev if e.status in ("missing", "requested")]}


def _flag(t: Task) -> str:
    d = t.due_date
    if t.kind == "limitation" and t.trigger_date and t.period_days:
        d = t.trigger_date + timedelta(days=t.period_days)
    if not d or t.done:
        return ""
    left = (d - date.today()).days
    return "overdue" if left < 0 else ("due_soon" if left <= 30 else "")


@router.get("/{case_id}/cockpit")
def cockpit(ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    cid = ctx.case.id
    tasks = db.scalars(select(Task).where(Task.case_id == cid, Task.done == False)).all()  # noqa: E712
    docs = db.scalars(select(Document).where(Document.case_id == cid)).all()
    runs = db.scalars(select(WorkflowRun).where(WorkflowRun.case_id == cid).order_by(WorkflowRun.created_at.desc()).limit(5)).all()
    matrix = evidence_matrix(ctx, db)
    unrev = db.scalar(select(func.count()).select_from(Extraction).where(Extraction.case_id == cid, Extraction.review_status == "pending"))
    return {"case": to_dict(ctx.case), "alerts": [{"task_id": str(t.id), "title": t.title, "flag": _flag(t), "due": (t.due_date.isoformat() if t.due_date else None),
                                                   "needs_review": not t.reviewed, "note": "Advocate must verify; limitation periods are never auto-assumed."}
                                                  for t in tasks if _flag(t) or not t.reviewed],
            "documents": {"total": len(docs), "unprocessed": sum(1 for d in docs if d.processing_status not in ("extracted",)), "pending_review_items": unrev},
            "evidence": {"issues_without_evidence": len(matrix["issues_without_evidence"]), "missing": len(matrix["missing_evidence"])},
            "recent_runs": [{"id": str(r.id), "kind": r.kind, "status": r.status, "created_at": r.created_at.isoformat()} for r in runs],
            "reports_awaiting_review": db.scalar(select(func.count()).select_from(Report).where(Report.case_id == cid, Report.status == "draft"))}


@router.get("/{case_id}/activity")
def activity(ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    cid = str(ctx.case.id)
    rows = [r for r in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(2000)).all()
            if r.resource_id == cid or (r.detail or {}).get("case_id") == cid][:100]
    return [{"action": r.action, "user_id": str(r.user_id) if r.user_id else None, "at": r.created_at.isoformat(), "resource_type": r.resource_type} for r in rows]


# ------------------------------------------------------------------ Case Twin (versioned structured representation)
def build_twin(db: Session, case: Case) -> dict:
    g = lambda m: db.scalars(select(m).where(m.case_id == case.id)).all()  # noqa: E731
    docs = g(Document)
    ext = db.scalars(select(Extraction).where(Extraction.case_id == case.id, Extraction.review_status != "rejected")).all()
    last_assess = db.scalars(select(Report).where(Report.case_id == case.id, Report.kind == "case_assessment", Report.status == "approved").order_by(Report.created_at.desc())).first()
    auth = []
    if last_assess:
        for s in last_assess.content["assessment"]["issues"]:
            auth += [{"issue": s["issue"], "title": a["title"], "pinpoint": a["pinpoint"], "chunk_id": a["chunk_id"]} for a in s["primary_authorities"]]
    return {"case": {"id": str(case.id), "title": case.title, "type": case.case_type, "jurisdiction": case.jurisdiction, "forum": case.forum},
            "parties": [{"name": p.name, "role": p.role, "relationship": p.relationship_to} for p in g(Party)],
            "facts": [{"id": str(f.id), "text": f.text, "disputed": f.disputed, "date": f.fact_date.isoformat() if f.fact_date else None, "document_id": str(f.document_id) if f.document_id else None, "page": f.page} for f in g(Fact)],
            "events": [{"date": e.event_date.isoformat() if e.event_date else None, "title": e.title, "document_id": str(e.document_id) if e.document_id else None, "page": e.page} for e in g(TimelineEvent)],
            "documents": [{"id": str(d.id), "filename": d.filename, "type": d.doc_type, "version": d.version, "status": d.processing_status} for d in docs],
            "extracted_facts": [{"kind": e.kind, "value": e.edited_value or e.value, "document_id": str(e.document_id), "page": e.page, "origin": e.origin, "review": e.review_status} for e in ext if e.kind in ("party", "date", "amount", "legal_ref", "deadline")][:300],
            "evidence": [{"title": e.title, "kind": e.kind, "status": e.status, "issues": e.issue_ids, "supports": e.supports} for e in g(EvidenceItem)],
            "legal_issues": [{"id": str(i.id), "title": i.title} for i in g(LegalIssue)],
            "authorities": auth, "authorities_note": "Only authorities from advocate-APPROVED assessments are included."}


@router.post("/{case_id}/twin/rebuild", status_code=201)
def rebuild_twin(ctx: CaseCtx = Depends(get_case_write), db: Session = Depends(get_db)):
    last = db.scalar(select(func.max(CaseTwinVersion.version)).where(CaseTwinVersion.case_id == ctx.case.id)) or 0
    data = build_twin(db, ctx.case)
    prev = db.scalar(select(CaseTwinVersion).where(CaseTwinVersion.case_id == ctx.case.id, CaseTwinVersion.version == last)) if last else None
    delta = {k: len(v) - (len(prev.data.get(k, [])) if prev else 0) for k, v in data.items() if isinstance(v, list)}
    v = CaseTwinVersion(case_id=ctx.case.id, version=last + 1, data={**data, "_delta_vs_previous": delta}, created_by=ctx.user.id)
    db.add(v)
    audit(db, ctx.user, "twin.rebuild", "case", ctx.case.id, {"version": last + 1})
    db.commit()
    return {"version": v.version, "data": v.data, "created_at": v.created_at.isoformat()}


@router.get("/{case_id}/twin")
def twin(version: int | None = None, ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    stmt = select(CaseTwinVersion).where(CaseTwinVersion.case_id == ctx.case.id)
    v = db.scalar(stmt.where(CaseTwinVersion.version == version) if version else stmt.order_by(CaseTwinVersion.version.desc()))
    versions = [x for (x,) in db.execute(select(CaseTwinVersion.version).where(CaseTwinVersion.case_id == ctx.case.id).order_by(CaseTwinVersion.version.desc())).all()]
    return {"versions": versions, "current": {"version": v.version, "data": v.data, "created_at": v.created_at.isoformat()} if v else None}
