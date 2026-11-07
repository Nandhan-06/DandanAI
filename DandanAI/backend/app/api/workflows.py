import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.util import to_dict
from app.core.config import get_settings
from app.database import get_db
from app.deps import CaseCtx, accessible_case_ids, case_access, get_case_advocate, get_current_user
from app.models import Report, User, WorkflowCheckpoint, WorkflowRun, WorkflowStep
from app.services import workflows as wf

router = APIRouter(prefix="/api/v1", tags=["agents"])


class AssessIn(BaseModel):
    as_of: date | None = None
    client_side: str | None = Field(None, description="tenant|landlord|employee|employer|prosecution|defence")
    use_documents: bool = True
    inject_failure: dict | None = None  # test-only; ignored in production / live mode


class DandanIn(BaseModel):
    incident: str = Field(min_length=20, max_length=20000)
    perspective: str = "neutral"  # prosecution | defence | neutral
    as_of: date | None = None
    inject_failure: dict | None = None


def _inject(body) -> dict | None:
    return body.inject_failure if (body.inject_failure and not get_settings().is_production) else None


@router.post("/cases/{case_id}/workflows/assessment", status_code=201)
def run_assessment(body: AssessIn, ctx: CaseCtx = Depends(get_case_advocate), db: Session = Depends(get_db)):
    run = wf.start_run(db, ctx.user, ctx.case.id, "case_assessment", {"client_side": body.client_side, "use_documents": body.use_documents},
                       as_of=body.as_of.isoformat() if body.as_of else None, jurisdiction=ctx.case.jurisdiction, inject=_inject(body))
    return _run_out(db, run)


@router.post("/cases/{case_id}/workflows/criminal", status_code=201)
def run_criminal(body: DandanIn, ctx: CaseCtx = Depends(get_case_advocate), db: Session = Depends(get_db)):
    if body.perspective not in ("prosecution", "defence", "neutral"):
        raise HTTPException(422, "perspective must be prosecution|defence|neutral")
    run = wf.start_run(db, ctx.user, ctx.case.id, "criminal_intelligence", {"incident": body.incident, "perspective": body.perspective},
                       as_of=body.as_of.isoformat() if body.as_of else None, jurisdiction=ctx.case.jurisdiction, inject=_inject(body))
    return _run_out(db, run)


def _run_out(db: Session, run: WorkflowRun) -> dict:
    steps = db.scalars(select(WorkflowStep).where(WorkflowStep.run_id == run.id).order_by(WorkflowStep.seq)).all()
    cps = db.scalars(select(WorkflowCheckpoint.after_node).where(WorkflowCheckpoint.run_id == run.id).order_by(WorkflowCheckpoint.seq)).all()
    return {**to_dict(run, exclude={"state", "input"}), "steps": [to_dict(s) for s in steps], "checkpoints": list(cps),
            "input": {k: v for k, v in (run.input or {}).items() if k != "incident"} | ({"incident_chars": len(run.input["incident"])} if run.input and "incident" in run.input else {})}


def _own_run(db: Session, user: User, run_id: uuid.UUID) -> WorkflowRun:
    run = db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    case_access(db, user, run.case_id)  # raises 404 if the user has no access to the case
    return run


@router.get("/workflows")
def list_runs(case_id: uuid.UUID | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = accessible_case_ids(db, user)
    stmt = select(WorkflowRun).where(WorkflowRun.case_id.in_(ids)) if ids else select(WorkflowRun).where(False)
    if case_id:
        stmt = stmt.where(WorkflowRun.case_id == case_id)
    return [to_dict(r, exclude={"state", "input"}) for r in db.scalars(stmt.order_by(WorkflowRun.created_at.desc()).limit(100)).all()]


@router.get("/workflows/{run_id}")
def get_run(run_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _run_out(db, _own_run(db, user, run_id))


@router.get("/workflows/{run_id}/state")
def get_state(run_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_run(db, user, run_id)
    return {"state": {k: v for k, v in (run.state or {}).items() if k != "params"}}


@router.post("/workflows/{run_id}/resume")
def resume(run_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_run(db, user, run_id)
    if user.role != "advocate":
        raise HTTPException(403, "Only advocates may resume workflows")
    if run.status != "failed":
        raise HTTPException(409, "Only failed runs can be resumed")
    return _run_out(db, wf.resume_run(db, run, user))


class ReviewIn(BaseModel):
    note: str | None = Field(None, max_length=2000)


def _review(run_id, body, approve, user, db):
    run = _own_run(db, user, run_id)
    if user.role != "advocate":
        raise HTTPException(403, "Only an advocate may approve or reject reports")
    try:
        rep = wf.review(db, user, run, approve, body.note)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"run_status": run.status, "report": to_dict(rep, exclude={"content"})}


@router.post("/workflows/{run_id}/approve")
def approve(run_id: uuid.UUID, body: ReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _review(run_id, body, True, user, db)


@router.post("/workflows/{run_id}/reject")
def reject(run_id: uuid.UUID, body: ReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _review(run_id, body, False, user, db)


# ------------------------------------------------------------------ reports
reports = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _own_report(db: Session, user: User, rid: uuid.UUID) -> Report:
    r = db.get(Report, rid)
    if not r:
        raise HTTPException(404, "Report not found")
    case_access(db, user, r.case_id)
    return r


@reports.get("")
def list_reports(case_id: uuid.UUID | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = accessible_case_ids(db, user)
    stmt = select(Report).where(Report.case_id.in_(ids)) if ids else select(Report).where(False)
    if case_id:
        stmt = stmt.where(Report.case_id == case_id)
    return [to_dict(r, exclude={"content", "markdown"}) for r in db.scalars(stmt.order_by(Report.created_at.desc())).all()]


@reports.get("/{rid}")
def get_report(rid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return to_dict(_own_report(db, user, rid))


@reports.get("/{rid}/export")
def export(rid: uuid.UUID, format: str = "md", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from fastapi import Response
    from app.services.audit import audit
    from app.services.reports import to_docx, to_pdf
    r = _own_report(db, user, rid)
    if format == "pdf":
        body, mt = to_pdf(r.markdown), "application/pdf"
    elif format == "docx":
        body, mt = to_docx(r.markdown), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif format == "md":
        body, mt = r.markdown.encode(), "text/markdown"
    else:
        raise HTTPException(422, "format must be md|pdf|docx")
    audit(db, user, "report.export", "report", r.id, {"format": format, "status": r.status})
    db.commit()
    return Response(body, media_type=mt, headers={"Content-Disposition": f'attachment; filename="dandanai-report-{str(r.id)[:8]}.{format}"'})
