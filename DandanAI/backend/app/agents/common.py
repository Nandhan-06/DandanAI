"""Shared agent infrastructure: typed state, retry policy, step logging, checkpoint persistence."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User, WorkflowCheckpoint, WorkflowRun, WorkflowStep
from app.services.observability import trace_event
from app.services.providers import LLM

MAX_ATTEMPTS = 3


class WorkflowState(TypedDict, total=False):
    run_id: str
    case_id: str
    org_id: str
    user_id: str
    kind: str
    params: dict
    as_of: str | None
    jurisdiction: str | None
    completed: list[str]
    inject: dict | None  # test-only fault injection (mock mode, non-production)
    inject_counts: dict
    # case assessment
    doc_analysis: dict
    research: dict
    assessment: dict
    adversarial: dict
    citation_report: dict
    verification_round: int
    strip_failed_citations: bool
    # criminal intelligence
    incident: dict
    classification: dict
    statutes: dict
    evidence_plan: dict
    precedents: dict
    punishment: dict
    flags: list[str]
    report: dict
    status: str


@dataclass
class Ctx:
    db: Session
    run: WorkflowRun
    user: User
    llm: LLM


class AgentValidationError(Exception):
    pass


def _seq(db: Session, model, run_id) -> int:
    return (db.scalar(select(func.max(model.seq)).where(model.run_id == run_id)) or 0) + 1


def log_step(ctx: Ctx, agent: str, status: str, attempt: int, summary: str | None = None, output: dict | None = None,
             error: str | None = None, ms: int = 0) -> None:
    ctx.db.add(WorkflowStep(run_id=ctx.run.id, seq=_seq(ctx.db, WorkflowStep, ctx.run.id), agent=agent, status=status, attempt=attempt,
                            summary=summary, output=output, error=error, duration_ms=ms))
    ctx.db.commit()
    trace_event("agent_step", {"run": str(ctx.run.id), "agent": agent, "status": status, "attempt": attempt, "ms": ms})


def checkpoint(ctx: Ctx, after_node: str, state: dict) -> None:
    safe = {k: v for k, v in state.items() if k != "inject_counts"}
    ctx.db.add(WorkflowCheckpoint(run_id=ctx.run.id, seq=_seq(ctx.db, WorkflowCheckpoint, ctx.run.id), after_node=after_node, state=safe))
    ctx.run.state = safe
    ctx.db.commit()


def make_node(ctx: Ctx, name: str, fn: Callable[[WorkflowState, Ctx], dict], summarize: Callable[[dict], str]):
    """Wrap an agent function with: skip-if-completed (resume), fault injection, retry policy, validation, logging, checkpoint."""
    def node(state: WorkflowState) -> dict:
        if name in (state.get("completed") or []):
            return {}
        last_err = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.time()
            try:
                inj = state.get("inject") or {}
                s = get_settings()
                if inj.get("agent") == name and not s.is_production and ctx.llm.is_mock:
                    counts = state.setdefault("inject_counts", {})
                    counts[name] = counts.get(name, 0) + 1
                    if counts[name] <= int(inj.get("fail_times", 1)):
                        raise RuntimeError(f"injected failure #{counts[name]} (test fault injection)")
                update = fn(state, ctx)
                new_state = {**state, **update, "completed": [*(state.get("completed") or []), name]}
                log_step(ctx, name, "ok", attempt, summarize(update), None, None, int((time.time() - t0) * 1000))
                checkpoint(ctx, name, new_state)
                return {**update, "completed": new_state["completed"]}
            except AgentValidationError as e:
                last_err = f"validation: {e}"
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
            ctx.db.rollback()
            final = attempt == MAX_ATTEMPTS
            log_step(ctx, name, "failed" if final else "retrying", attempt, None, None, last_err[:500], int((time.time() - t0) * 1000))
        raise RuntimeError(f"{name} failed after {MAX_ATTEMPTS} attempts: {last_err}")
    return node


def skip_step(ctx: Ctx, agent: str, why: str) -> None:
    log_step(ctx, agent, "skipped", 1, why)
