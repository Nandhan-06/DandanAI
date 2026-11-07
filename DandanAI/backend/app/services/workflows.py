"""Runs / resumes LangGraph workflows with persistence, and handles human approval."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import case_graph, criminal
from app.agents.common import Ctx
from app.models import Report, User, WorkflowCheckpoint, WorkflowRun
from app.services.audit import audit
from app.services.providers import get_llm, mode


def start_run(db: Session, user: User, case_id: uuid.UUID, kind: str, params: dict, *, as_of: str | None, jurisdiction: str | None,
              inject: dict | None = None) -> WorkflowRun:
    run = WorkflowRun(org_id=user.org_id, case_id=case_id, requested_by=user.id, kind=kind, status="running", mode=mode()["overall"], input=params)
    db.add(run)
    db.flush()
    audit(db, user, f"workflow.{kind}.start", "workflow_run", run.id, {"case_id": str(case_id)})
    db.commit()
    state = {"run_id": str(run.id), "case_id": str(case_id), "org_id": str(user.org_id), "user_id": str(user.id), "kind": kind, "params": params,
             "as_of": as_of, "jurisdiction": jurisdiction, "completed": [], "inject": inject, "inject_counts": {}, "flags": []}
    return execute(db, run, user, state)


def execute(db: Session, run: WorkflowRun, user: User, state: dict) -> WorkflowRun:
    ctx = Ctx(db=db, run=run, user=user, llm=get_llm())
    graph = (case_graph if run.kind == "case_assessment" else criminal).build_graph(ctx)
    try:
        final = graph.invoke(state, {"recursion_limit": 40})
        run.status = "awaiting_review"
        run.state = {k: v for k, v in final.items() if k not in ("inject_counts",)}
        run.error = None
    except Exception as e:  # noqa: BLE001
        db.rollback()
        run = db.get(WorkflowRun, run.id)
        run.status = "failed"
        run.error = f"{type(e).__name__}: {e}"[:800]
    audit(db, user, f"workflow.{run.kind}.{run.status}", "workflow_run", run.id)
    db.commit()
    return run


def resume_run(db: Session, run: WorkflowRun, user: User) -> WorkflowRun:
    """Resume a failed run from its last persisted checkpoint (completed agents are skipped)."""
    cp = db.scalars(select(WorkflowCheckpoint).where(WorkflowCheckpoint.run_id == run.id).order_by(WorkflowCheckpoint.seq.desc())).first()
    base = dict(cp.state) if cp else {"run_id": str(run.id), "case_id": str(run.case_id), "org_id": str(run.org_id), "user_id": str(run.requested_by),
                                      "kind": run.kind, "params": run.input or {}, "completed": [], "flags": []}
    base["inject"] = None  # injected faults are one-shot
    base["inject_counts"] = {}
    run.status, run.error = "running", None
    db.commit()
    return execute(db, run, user, base)


def review(db: Session, user: User, run: WorkflowRun, approve: bool, note: str | None) -> Report:
    rep = db.get(Report, run.report_id) if run.report_id else None
    if not rep or run.status != "awaiting_review":
        raise ValueError("Run is not awaiting review")
    rep.status = "approved" if approve else "rejected"
    rep.reviewed_by, rep.review_note, rep.reviewed_at = user.id, note, datetime.now(timezone.utc)
    if approve:  # strip the draft banner now that a human approved it
        rep.markdown = rep.markdown.replace("> **DRAFT — NOT REVIEWED.** Requires advocate approval before reliance.\n", "> **APPROVED by advocate review.** Verify all sources independently.\n")
    run.status = "approved" if approve else "rejected"
    audit(db, user, f"report.{rep.status}", "report", rep.id, {"run_id": str(run.id), "note": note})
    db.commit()
    return rep
