"""LangGraph multi-agent case-assessment workflow.

Agents (each has a distinct input, output and validation step):
 1 Document Analysis   - consolidates stored extractions, cross-document inconsistencies, missing documents
 2 Legal Research      - jurisdiction/date-filtered hybrid retrieval per legal issue
 3 Case Assessment     - evidence-to-issue mapping, gaps, cited analysis (no success probabilities)
 4 Adversarial Review  - contrary authorities, objections, weak-point detection
 5 Citation Verification - verifies every citation, flags uncited authorities; routes retry or human review
Routing is explicit (conditional edges). State is typed. Each node is retried (3x), logged and checkpointed."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from langgraph.graph import END, StateGraph
from sqlalchemy import select

from app.agents.common import AgentValidationError, Ctx, WorkflowState, make_node
from app.models import Case, Document, EvidenceItem, Extraction, Fact, LegalIssue, Task
from app.services import guardrails
from app.services.rag import find_uncited_authorities, search_legal, verify_citation
from app.services.reports import cite_line, render_markdown

OPPOSITE = {"supports_tenant": "supports_landlord", "supports_landlord": "supports_tenant", "supports_employee": "supports_employer",
            "supports_employer": "supports_employee", "supports_prosecution": "supports_defence", "supports_defence": "supports_prosecution"}
SIDE_STANCE = {"tenant": "supports_tenant", "landlord": "supports_landlord", "employee": "supports_employee", "employer": "supports_employer",
               "prosecution": "supports_prosecution", "defence": "supports_defence"}
EXPECTED_DOCS = {"tenancy": ["rental_agreement", "legal_notice"], "employment": ["employment_agreement"], "property": ["property_agreement"],
                 "criminal": ["complaint", "evidence"], "civil": ["legal_notice"]}


def _case(ctx: Ctx) -> Case:
    return ctx.db.get(Case, ctx.run.case_id)


# ------------------------------------------------------------------ Agent 1
def document_analysis(state: WorkflowState, ctx: Ctx) -> dict:
    case = _case(ctx)
    docs = ctx.db.scalars(select(Document).where(Document.case_id == case.id).order_by(Document.created_at)).all()
    docs = [d for d in docs if d.processing_status in ("extracted",)]
    out_docs, by_kind = [], defaultdict(list)
    for d in docs:
        ex = ctx.db.scalars(select(Extraction).where(Extraction.document_id == d.id, Extraction.review_status != "rejected")).all()
        item = {"document_id": str(d.id), "filename": d.filename, "doc_type": d.doc_type, "version": d.version, "items": {}}
        for e in ex:
            val = e.edited_value or e.value
            if e.origin == "explicit" and e.page is None and not e.locator:
                raise AgentValidationError(f"explicit extraction {e.id} lacks page provenance")
            item["items"].setdefault(e.kind, []).append({"value": val, "page": e.page, "origin": e.origin, "label": e.label})
            by_kind[(e.kind, (e.label or "").lower())].append((d.filename, val, e.page))
        out_docs.append(item)
    inconsistencies = []
    for (kind, label), vals in by_kind.items():
        if kind == "amount" and label and len({v for _, v, _ in vals}) > 1:
            inconsistencies.append({"value": f"Differing amounts for '{label}': " + "; ".join(f"{f} p.{p}: {v}" for f, v, p in vals), "origin": "ai_inferred"})
    names = defaultdict(set)
    for d in out_docs:
        for p in d["items"].get("party", []):
            if p["label"]:
                names[p["label"].lower()].add(p["value"].lower())
    for role, vs in names.items():
        if len(vs) > 1:
            inconsistencies.append({"value": f"Different names for the same role '{role}' across documents: {sorted(vs)}", "origin": "ai_inferred"})
    have = {d.doc_type for d in docs}
    expected = EXPECTED_DOCS.get((case.case_type or "").lower(), [])
    missing_docs = [{"value": f"No '{t}' document uploaded", "origin": "ai_inferred"} for t in expected if t not in have]
    unprocessed = [d.filename for d in ctx.db.scalars(select(Document).where(Document.case_id == case.id)).all() if d.processing_status != "extracted"]
    return {"doc_analysis": {"documents": out_docs, "inconsistencies": inconsistencies, "missing_documents": missing_docs,
                             "unprocessed_documents": unprocessed, "document_count": len(out_docs)}}


# ------------------------------------------------------------------ Agent 2
def legal_research(state: WorkflowState, ctx: Ctx) -> dict:
    case = _case(ctx)
    as_of = date.fromisoformat(state["as_of"]) if state.get("as_of") else None
    issues = ctx.db.scalars(select(LegalIssue).where(LegalIssue.case_id == case.id)).all()
    queries = [(i.title, f"{i.title} {i.description or ''}") for i in issues]
    refs = [r["value"] for d in (state.get("doc_analysis") or {}).get("documents", []) for r in d["items"].get("legal_ref", [])][:5]
    for r in refs:
        queries.append((f"Referenced in documents: {r}", r))
    if not queries:
        queries.append(("Case description", f"{case.title} {case.description or ''}"))
    results, seen, authorities, gaps = [], set(), [], []
    for label, q in queries:
        q, flags = guardrails.clean_input(q, max_chars=2000)
        res = search_legal(ctx.db, q, jurisdiction=state.get("jurisdiction") or case.jurisdiction, as_of=as_of, top_k=5)
        results.append({"issue": label, "query": q[:200], "confidence": res["confidence"], "coverage_gaps": res["coverage_gaps"], "hit_count": len(res["hits"]),
                        "citations": [h["citation"] for h in res["hits"]], "jurisdictions_searched": res["jurisdictions_searched"], "input_flags": flags})
        gaps += [f"{label}: {g}" for g in res["coverage_gaps"]]
        for h in res["hits"]:
            if h["citation"]["chunk_id"] not in seen:
                seen.add(h["citation"]["chunk_id"])
                authorities.append(h["citation"])
    for a in authorities:
        if not a.get("chunk_id") or not a.get("title"):
            raise AgentValidationError("authority without chunk_id/title")
    return {"research": {"per_issue": results, "authorities": authorities, "coverage_gaps": gaps, "searched_as_of": state.get("as_of"),
                         "insufficient_support": not authorities}}


# ------------------------------------------------------------------ Agent 3
def case_assessment(state: WorkflowState, ctx: Ctx) -> dict:
    case = _case(ctx)
    research = state.get("research") or {}
    banned = set()
    if state.get("strip_failed_citations"):
        banned = {v["chunk_id"] for v in (state.get("citation_report") or {}).get("verdicts", []) if v["verdict"] == "failed"}
    issues = ctx.db.scalars(select(LegalIssue).where(LegalIssue.case_id == case.id)).all()
    facts = ctx.db.scalars(select(Fact).where(Fact.case_id == case.id)).all()
    evidence = ctx.db.scalars(select(EvidenceItem).where(EvidenceItem.case_id == case.id)).all()
    tasks = ctx.db.scalars(select(Task).where(Task.case_id == case.id, Task.done == False)).all()  # noqa: E712
    per_issue = {r["issue"]: r for r in research.get("per_issue", [])}
    sections = []
    for iss in issues or [None]:
        title = iss.title if iss else "General (no legal issues recorded)"
        r = per_issue.get(title) or (research.get("per_issue") or [{}])[0]
        cites = [c for c in r.get("citations", []) if c["chunk_id"] not in banned]
        prim = [c for c in cites if c["authority_class"] == "primary"]
        ev = [e for e in evidence if iss and str(iss.id) in (e.issue_ids or [])]
        sections.append({"issue": title, "issue_id": str(iss.id) if iss else None,
                         "primary_authorities": prim, "secondary_authorities": [c for c in cites if c["authority_class"] != "primary"],
                         "evidence_for": [{"id": str(e.id), "title": e.title, "supports": e.supports, "status": e.status} for e in ev],
                         "evidence_gaps": (["No evidence mapped to this issue"] if iss and not ev else []) + [f"Evidence requested but missing: {e.title}" for e in ev if e.status == "missing"],
                         "disputed_facts": [f.text for f in facts if f.disputed],
                         "support_level": r.get("confidence", "none"),
                         "analysis": (f"{len(prim)} primary and {len(cites) - len(prim)} secondary sources were retrieved for this issue. "
                                      "Each source must be read in full and verified by the advocate; this section does not state how a court will decide.")
                         if cites else "Insufficient supporting authority was found in the knowledge base for this issue. No legal conclusion is offered."})
    deadlines = [{"title": t.title, "due": t.due_date.isoformat() if t.due_date else None, "kind": t.kind, "reviewed": t.reviewed,
                  "flag": "OVERDUE — advocate review" if t.due_date and t.due_date < date.today() else ("DUE WITHIN 30 DAYS — advocate review" if t.due_date and (t.due_date - date.today()).days <= 30 else "")}
                 for t in tasks if t.kind in ("deadline", "limitation") or t.due_date]
    for t in tasks:
        if t.kind == "limitation" and t.trigger_date and t.period_days:
            from datetime import timedelta
            deadlines.append({"title": f"Limitation (advocate-entered): {t.title}", "due": (t.trigger_date + timedelta(days=t.period_days)).isoformat(), "kind": "limitation", "reviewed": t.reviewed, "flag": "Computed from advocate-entered period — verify"})
    narrative = ctx.llm.complete("You assist advocates. Never predict outcomes. Cite only provided sources.",
                                 f"Summarise the case '{case.title}' in neutral terms: {len(issues)} issues, {len(facts)} facts, {len(evidence)} evidence items.")
    narrative, flags = guardrails.check_output(narrative)
    out = {"case_title": case.title, "jurisdiction": case.jurisdiction, "summary": narrative, "issues": sections,
           "document_gaps": (state.get("doc_analysis") or {}).get("missing_documents", []), "inconsistencies": (state.get("doc_analysis") or {}).get("inconsistencies", []),
           "deadline_flags": deadlines, "uncertainty": research.get("coverage_gaps", []),
           "statement": "Preliminary, human-review-required assessment. No success probability or outcome prediction is given."}
    all_flags = sorted(set(flags + guardrails.scan_structure(out)))
    if "outcome_prediction_redacted" in all_flags:
        raise AgentValidationError("assessment contained outcome-prediction language")
    return {"assessment": out, "flags": sorted(set((state.get("flags") or []) + all_flags)), "strip_failed_citations": False}


# ------------------------------------------------------------------ Agent 4
def adversarial_review(state: WorkflowState, ctx: Ctx) -> dict:
    case = _case(ctx)
    side = SIDE_STANCE.get(((state.get("params") or {}).get("client_side") or "").lower())
    as_of = date.fromisoformat(state["as_of"]) if state.get("as_of") else None
    asm = state["assessment"]
    objections, adverse, seen = [], [], set()
    for sec in asm["issues"]:
        if not sec["primary_authorities"]:
            objections.append({"severity": "high", "issue": sec["issue"], "text": "No primary legal authority supports this issue; the position is unsupported."})
        if sec["evidence_gaps"]:
            objections.append({"severity": "medium", "issue": sec["issue"], "text": "; ".join(sec["evidence_gaps"])})
        q = f"{case.case_type or ''} {sec['issue']}"
        stances = [OPPOSITE[side]] if side else ["supports_tenant", "supports_landlord", "supports_employee", "supports_employer", "supports_prosecution", "supports_defence"]
        for st in stances:
            res = search_legal(ctx.db, q, jurisdiction=state.get("jurisdiction") or case.jurisdiction, as_of=as_of, stance=st, instrument_types=["judgment"], top_k=2)
            for h in res["hits"]:
                if h["citation"]["chunk_id"] not in seen:
                    seen.add(h["citation"]["chunk_id"])
                    adverse.append({**h["citation"], "for_issue": q, "why_adverse": f"Stance tag '{st}'" + (" (opposes client side)" if side else " (side not specified)")})
    for inc in asm.get("inconsistencies", []):
        objections.append({"severity": "medium", "issue": None, "text": inc["value"]})
    for d in asm.get("deadline_flags", []):
        if d["flag"].startswith("OVERDUE"):
            objections.append({"severity": "high", "issue": None, "text": f"Overdue item: {d['title']}"})
    for m in asm.get("document_gaps", []):
        objections.append({"severity": "low", "issue": None, "text": m["value"]})
    if state["research"].get("insufficient_support"):
        objections.append({"severity": "high", "issue": None, "text": "Knowledge base returned no supporting authority at all (coverage gap)."})
    return {"adversarial": {"client_side": (state.get("params") or {}).get("client_side"), "objections": objections, "adverse_authorities": adverse,
                            "note": "Adverse authorities are retrieved by stance metadata/semantics and must be read in full by the advocate."}}


# ------------------------------------------------------------------ Agent 5
def citation_verification(state: WorkflowState, ctx: Ctx) -> dict:
    as_of = date.fromisoformat(state["as_of"]) if state.get("as_of") else None
    cites = []
    for sec in state["assessment"]["issues"]:
        cites += sec["primary_authorities"] + sec["secondary_authorities"]
    cites += state["adversarial"]["adverse_authorities"]
    uniq = {c["chunk_id"]: c for c in cites}
    verdicts = [verify_citation(ctx.db, c, as_of=as_of) for c in uniq.values()]
    text = " ".join([state["assessment"]["summary"]] + [s["analysis"] for s in state["assessment"]["issues"]])
    uncited = find_uncited_authorities(text, [c["title"] for c in uniq.values()])
    failed = [v for v in verdicts if v["verdict"] == "failed"]
    warn = [v for v in verdicts if v["verdict"] != "verified" and v["verdict"] != "failed"]
    status = "fail" if failed or uncited else ("pass_with_warnings" if warn or not verdicts else "pass")
    return {"citation_report": {"verdicts": verdicts, "uncited_authority_mentions": uncited, "failed": len(failed), "warnings": len(warn), "status": status,
                                "total": len(verdicts)}, "verification_round": (state.get("verification_round") or 0) + 1}


# ------------------------------------------------------------------ finalize (human-review gate)
def finalize(state: WorkflowState, ctx: Ctx) -> dict:
    from app.models import Report
    case = _case(ctx)
    asm, adv, cr, res = state["assessment"], state["adversarial"], state["citation_report"], state["research"]
    synthetic = any(c.get("is_synthetic") for c in res["authorities"])
    sections = [("Case summary", [asm["summary"], "", f"Jurisdiction: {asm['jurisdiction'] or 'not specified'}"]),
                ("Issues, authorities and evidence", [])]
    for s in asm["issues"]:
        L = sections[1][1]
        L += [f"### {s['issue']}", f"*Retrieval support:* {s['support_level']}", s["analysis"], ""]
        L += [f"- Primary: {cite_line(c)}" for c in s["primary_authorities"]] + [f"- Secondary: {cite_line(c)}" for c in s["secondary_authorities"]]
        L += [f"- Evidence: {e['title']} ({e['supports']}, {e['status']})" for e in s["evidence_for"]] + [f"- GAP: {g}" for g in s["evidence_gaps"]] + [""]
    sections += [("Adverse review (objections)", [f"- [{o['severity'].upper()}] {o['text']}" for o in adv["objections"]] or ["- None identified"]),
                 ("Adverse / contrary authorities", [f"- {cite_line(a)} (for: {a['for_issue']})" for a in adv["adverse_authorities"]] or ["- None retrieved"]),
                 ("Deadlines and limitation flags (advocate review)", [f"- {d['title']} — {d['due']} {d['flag']}" for d in asm["deadline_flags"]] or ["- None"]),
                 ("Coverage gaps and uncertainty", [f"- {g}" for g in asm["uncertainty"]] or ["- None reported"]),
                 ("Citation verification", [f"Status: **{cr['status']}** ({cr['total']} citations, {cr['failed']} failed, {cr['warnings']} warnings)"] + [f"- Uncited authority mention: {u}" for u in cr["uncited_authority_mentions"]])]
    mode = ctx.run.mode
    md = render_markdown(f"Preliminary Case Assessment — {case.title}", sections, mode=mode, status="draft", synthetic=synthetic,
                         meta={"Generated": date.today().isoformat(), "Sources as of": state.get("as_of") or "current law"})
    rep = Report(org_id=ctx.run.org_id, case_id=case.id, run_id=ctx.run.id, kind="case_assessment", title=f"Case assessment — {case.title}",
                 content={"assessment": asm, "adversarial": adv, "citation_report": cr, "research_gaps": res["coverage_gaps"], "flags": state.get("flags", [])},
                 markdown=md, status="draft", mode=mode, created_by=ctx.run.requested_by)
    ctx.db.add(rep)
    ctx.db.flush()
    ctx.run.report_id = rep.id
    return {"report": {"id": str(rep.id)}, "status": "awaiting_review"}


# ------------------------------------------------------------------ routing
def route_start(state: WorkflowState) -> str:
    return "document_analysis" if (state.get("params") or {}).get("use_documents", True) else "legal_research"


def route_after_verification(state: WorkflowState) -> str:
    cr = state.get("citation_report") or {}
    if cr.get("status") == "fail" and (state.get("verification_round") or 0) < 2:
        return "retry_assessment"
    return "finalize"


def build_graph(ctx: Ctx):
    g = StateGraph(WorkflowState)
    g.add_node("document_analysis", make_node(ctx, "document_analysis", document_analysis, lambda u: f"{u['doc_analysis']['document_count']} documents analysed; {len(u['doc_analysis']['inconsistencies'])} inconsistencies; {len(u['doc_analysis']['missing_documents'])} missing documents"))
    g.add_node("legal_research", make_node(ctx, "legal_research", legal_research, lambda u: f"{len(u['research']['authorities'])} authorities; {len(u['research']['coverage_gaps'])} coverage gaps"))
    g.add_node("case_assessment", make_node(ctx, "case_assessment", case_assessment, lambda u: f"{len(u['assessment']['issues'])} issue sections drafted"))
    g.add_node("adversarial_review", make_node(ctx, "adversarial_review", adversarial_review, lambda u: f"{len(u['adversarial']['objections'])} objections; {len(u['adversarial']['adverse_authorities'])} adverse authorities"))
    g.add_node("citation_verification", make_node(ctx, "citation_verification", citation_verification, lambda u: f"citations {u['citation_report']['status']} ({u['citation_report']['failed']} failed)"))

    def retry_assessment(state: WorkflowState) -> dict:
        # re-open assessment/adversarial/verification with failed citations stripped
        done = [n for n in state.get("completed", []) if n not in ("case_assessment", "adversarial_review", "citation_verification")]
        return {"completed": done, "strip_failed_citations": True}

    g.add_node("retry_assessment", retry_assessment)
    g.add_node("finalize", make_node(ctx, "human_review_gate", finalize, lambda u: "report drafted; awaiting human approval"))
    g.set_conditional_entry_point(route_start, {"document_analysis": "document_analysis", "legal_research": "legal_research"})
    g.add_edge("document_analysis", "legal_research")
    g.add_edge("legal_research", "case_assessment")
    g.add_edge("case_assessment", "adversarial_review")
    g.add_edge("adversarial_review", "citation_verification")
    g.add_conditional_edges("citation_verification", route_after_verification, {"retry_assessment": "retry_assessment", "finalize": "finalize"})
    g.add_edge("retry_assessment", "case_assessment")
    g.add_edge("finalize", END)
    return g.compile()
