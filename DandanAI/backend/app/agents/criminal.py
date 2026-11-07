"""DandanAI Criminal Intelligence Engine (LangGraph).

incident_analysis -> crime_classification -> statute_mapping -> evidence_planner -> precedent_research
 -> punishment_compensation -> citation_verification -> finalize (human review gate)
Never predicts guilt/conviction/acquittal. Candidate provisions stay 'candidate' until a verified,
non-synthetic source supports them."""
from __future__ import annotations

import re
from datetime import date

from langgraph.graph import END, StateGraph
from sqlalchemy import select

from app.agents.case_graph import OPPOSITE, SIDE_STANCE
from app.agents.common import AgentValidationError, Ctx, WorkflowState, make_node
from app.models import Case, EvidenceItem, Report
from app.services import docintel, guardrails
from app.services.providers import tokenize
from app.services.rag import search_legal, verify_citation
from app.services.reports import cite_line, render_markdown

# Candidate offence taxonomy. real_ref values come from model background knowledge and are UNVERIFIED candidates:
# the advocate must confirm them against India Code / official gazette text.
OFFENCES = {
    "theft": dict(label="Theft", indicators=["stole", "stolen", "theft", "took away", "snatched", "missing from", "pickpocket", "burglary", "without consent", "removed"],
                  real_ref="Candidate (unverified): Bharatiya DandanAI Sanhita, 2023 — theft provision (s.303)",
                  elements=["dishonest intention", "movable property", "possession of another", "without consent", "movement of the property"],
                  element_hints={"dishonest intention": ["dishonest", "intend", "sold", "pawn", "stole"], "movable property": ["phone", "laptop", "bike", "cash", "jewel", "gold", "wallet", "vehicle", "property", "money", "goods"],
                                 "possession of another": ["my", "owner", "belong", "possession", "from the"], "without consent": ["without", "no permission", "not permitted", "without my consent", "stole", "snatched"],
                                 "movement of the property": ["took", "carried", "removed", "moved", "taken", "snatched", "stole"]},
                  evidence=["Complaint / FIR copy", "Proof of ownership (invoice, receipt, registration)", "CCTV or other video footage", "Witness statements", "Recovery / seizure memo and panchnama", "Valuation of the property", "Chain-of-custody record for recovered items"]),
    "cheating": dict(label="Cheating", indicators=["cheated", "deceived", "fraud", "false promise", "fake", "misrepresent", "induced", "duped", "scam"],
                     real_ref="Candidate (unverified): Bharatiya DandanAI Sanhita, 2023 — cheating provision (s.318)",
                     elements=["deception", "fraudulent or dishonest inducement", "delivery of property or consent", "resulting damage or harm"],
                     element_hints={"deception": ["deceiv", "false", "fake", "misrepresent", "lied", "fraud"], "fraudulent or dishonest inducement": ["induc", "promis", "assur", "convinc", "persuad"],
                                    "delivery of property or consent": ["paid", "transferred", "gave", "delivered", "deposit", "handed"], "resulting damage or harm": ["loss", "lost", "damage", "harm", "defraud"]},
                     evidence=["Written/electronic communications showing the representation", "Payment and bank-transfer proof", "Documents the accused relied on or issued", "Identity/KYC details of the accused", "Witness statements", "Demand notice and any reply"]),
    "cyber_fraud": dict(label="Cyber fraud / online financial fraud", indicators=["otp", "online", "upi", "phishing", "bank account", "credentials", "password", "hacked", "link", "internet banking", "card", "cyber"],
                        real_ref="Candidate (unverified): Information Technology Act, 2000 — computer-related offences (e.g. ss.66C/66D) read with Bharatiya DandanAI Sanhita, 2023",
                        elements=["use of computer resource or credentials of another", "dishonest or fraudulent intention", "wrongful gain or loss"],
                        element_hints={"use of computer resource or credentials of another": ["otp", "password", "credential", "upi", "net banking", "link", "phish", "card"], "dishonest or fraudulent intention": ["fraud", "dishonest", "fake", "scam", "unauthori"],
                                       "wrongful gain or loss": ["debited", "lost", "loss", "withdrawn", "transferred", "deducted", "rs", "₹"]},
                        evidence=["Bank statements and transaction logs", "IP address / device / intermediary logs", "SMS, OTP and call records", "Screenshots with metadata", "Certification of electronic records (as required by law — advocate to confirm)", "Cybercrime portal complaint acknowledgment", "Device seizure and forensic image"]),
    "hurt": dict(label="Hurt / bodily injury", indicators=["hit", "beat", "assault", "injur", "slapped", "attacked", "wound", "stabbed", "punched"],
                 real_ref="Candidate (unverified): Bharatiya DandanAI Sanhita, 2023 — hurt provisions (s.115 and related)",
                 elements=["act causing bodily pain, disease or infirmity", "voluntarily"],
                 element_hints={"act causing bodily pain, disease or infirmity": ["hit", "beat", "injur", "pain", "wound", "slapped", "punched", "stabbed"], "voluntarily": ["deliberate", "intentional", "attacked", "suddenly", "hit", "beat"]},
                 evidence=["Medical / MLC report", "Photographs of injuries", "Witness statements", "Weapon or object used (if any)", "FIR / complaint copy"]),
    "criminal_intimidation": dict(label="Criminal intimidation", indicators=["threat", "threaten", "warned", "will kill", "harm you", "blackmail", "intimidat"],
                                  real_ref="Candidate (unverified): Bharatiya DandanAI Sanhita, 2023 — criminal intimidation (s.351)",
                                  elements=["threat of injury", "intent to cause alarm or to compel an act"],
                                  element_hints={"threat of injury": ["threat", "kill", "harm", "hurt", "warned"], "intent to cause alarm or to compel an act": ["scare", "alarm", "force", "pressure", "compel", "demand"]},
                                  evidence=["Messages / call recordings containing the threat", "Call detail records", "Witness statements", "Complaint copy"]),
    "breach_of_trust": dict(label="Criminal breach of trust", indicators=["entrusted", "misappropriat", "embezzl", "trust", "cash handed", "custody", "kept the money"],
                            real_ref="Candidate (unverified): Bharatiya DandanAI Sanhita, 2023 — criminal breach of trust (s.316)",
                            elements=["entrustment", "dominion over property", "dishonest misappropriation or conversion"],
                            element_hints={"entrustment": ["entrust", "handed", "gave", "custody", "trust"], "dominion over property": ["custody", "control", "kept", "held", "managed"], "dishonest misappropriation or conversion": ["misappropriat", "embezzl", "own use", "refused to return", "converted", "did not return"]},
                            evidence=["Entrustment documents / agreement", "Accounts, ledgers, audit report", "Demand notice and reply", "Bank records", "Witness statements"]),
    "extortion": dict(label="Extortion", indicators=["extort", "demanded money", "pay or", "ransom"], real_ref="Candidate (unverified): Bharatiya DandanAI Sanhita, 2023 — extortion (s.308)",
                      elements=["fear of injury", "dishonest inducement to deliver property"], element_hints={}, evidence=["Messages/recordings of demands", "Payment proof", "Witness statements"]),
    "criminal_trespass": dict(label="Criminal trespass", indicators=["trespass", "entered my house", "broke into", "unlawfully entered"], real_ref="Candidate (unverified): Bharatiya DandanAI Sanhita, 2023 — trespass provisions (s.329)",
                              elements=["entry into property in possession of another", "intent to commit an offence or annoy"], element_hints={}, evidence=["Site photographs", "CCTV", "Witness statements"]),
}


def _incident_text(state: WorkflowState) -> str:
    return (state.get("incident") or {}).get("text") or (state.get("params") or {}).get("incident", "")


def incident_analysis(state: WorkflowState, ctx: Ctx) -> dict:
    raw = (state.get("params") or {}).get("incident", "")
    text, flags = guardrails.clean_input(raw)
    if len(text) < 20:
        raise AgentValidationError("incident description too short (need at least 20 characters)")
    an = docintel.analyse([(1, text)])
    items = an["items"]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    facts = [{"text": s, "origin": "explicit"} for s in sentences[:25]]
    low = text.lower()
    to_confirm = []
    if not any(i["kind"] == "date" for i in items):
        to_confirm.append("Date/time of the incident is not stated")
    if not re.search(r"\b(at|near|in|inside|outside)\s+[A-Z][\w ]{2,}", text):
        to_confirm.append("Place of the incident is not clearly stated")
    if not any(w in low for w in ("accused", "suspect", "he ", "she ", "they ", "unknown person", "stranger")):
        to_confirm.append("Identity or description of the alleged offender is not stated")
    return {"incident": {"text": text, "facts": facts, "dates": [i["value"] for i in items if i["kind"] == "date"], "amounts": [i["value"] for i in items if i["kind"] == "amount"],
                         "facts_to_confirm": to_confirm, "input_flags": flags, "note": "Facts are taken verbatim from the description; nothing is verified."},
            "flags": sorted(set((state.get("flags") or []) + flags))}


def crime_classification(state: WorkflowState, ctx: Ctx) -> dict:
    low = _incident_text(state).lower()
    cands = []
    for key, o in OFFENCES.items():
        hits = [w for w in o["indicators"] if w in low]
        if hits:
            cands.append({"offence_key": key, "label": o["label"], "matched_indicators": hits, "indicator_score": len(hits), "status": "candidate_unverified",
                          "reference_candidate": o["real_ref"]})
    cands.sort(key=lambda c: -c["indicator_score"])
    return {"classification": {"candidates": cands[:5], "no_candidate": not cands,
                               "note": "Candidates are keyword-indicator matches for advocate consideration. They are not findings that any offence was committed, and say nothing about guilt."}}


def statute_mapping(state: WorkflowState, ctx: Ctx) -> dict:
    case = ctx.db.get(Case, ctx.run.case_id)
    low = _incident_text(state).lower()
    as_of = date.fromisoformat(state["as_of"]) if state.get("as_of") else None
    mapped = []
    for c in state["classification"]["candidates"]:
        o = OFFENCES[c["offence_key"]]
        res = search_legal(ctx.db, f"{o['label']} elements punishment", jurisdiction=state.get("jurisdiction") or case.jurisdiction, as_of=as_of, offence=c["offence_key"],
                           instrument_types=["act", "rule", "notification"], top_k=2)
        provs = [h["citation"] for h in res["hits"]]
        elements = o["elements"]
        for p in provs:
            m = re.search(r"Elements:\s*(.+?)\.\s*Punishment", p["excerpt"] + " ", re.S)
            if m:
                elements = [e.strip() for e in m.group(1).split(";")]
                break
        emap = []
        for el in elements:
            hints = next((v for k, v in o["element_hints"].items() if k.lower() == el.lower()), [])
            present = [h for h in hints if h in low]
            emap.append({"element": el, "status": "facts_present" if present else ("not_evident" if hints else "unclear"), "matched_terms": present,
                         "note": "Keyword match only — advocate must assess against the actual facts and evidence."})
        if not provs:
            vstat = "unsupported_no_source_in_knowledge_base"
        elif all(p["is_synthetic"] for p in provs):
            vstat = "corpus_synthetic_only"
        elif any(p["verification_status"] == "human_verified" for p in provs):
            vstat = "verified_by_authoritative_source"
        else:
            vstat = "source_found_unverified"
        mapped.append({"offence_key": c["offence_key"], "label": c["label"], "reference_candidate": o["real_ref"], "verification_status": vstat,
                       "supporting_provisions": provs, "element_mapping": emap, "coverage_gaps": res["coverage_gaps"]})
    return {"statutes": {"mapped": mapped, "rule": "A candidate provision is 'verified' only when an authoritative, human-verified, non-synthetic source supports it."}}


def evidence_planner(state: WorkflowState, ctx: Ctx) -> dict:
    held = [e.title.lower() for e in ctx.db.scalars(select(EvidenceItem).where(EvidenceItem.case_id == ctx.run.case_id, EvidenceItem.status == "held")).all()]
    plan = []
    for m in state["statutes"]["mapped"]:
        cats = OFFENCES[m["offence_key"]]["evidence"]
        rows = [{"item": e, "status": "possibly_held" if any(w in h for h in held for w in tokenize(e)[:2]) else "gap"} for e in cats]
        plan.append({"offence_key": m["offence_key"], "label": m["label"], "checklist": rows, "gaps": [r["item"] for r in rows if r["status"] == "gap"]})
    return {"evidence_plan": {"per_offence": plan, "note": "Generic evidence categories for advocate/investigator consideration; not a statement of what the case has."}}


def precedent_research(state: WorkflowState, ctx: Ctx) -> dict:
    case = ctx.db.get(Case, ctx.run.case_id)
    persp = ((state.get("params") or {}).get("perspective") or "neutral").lower()
    mine = SIDE_STANCE.get(persp)
    as_of = date.fromisoformat(state["as_of"]) if state.get("as_of") else None
    out = []
    for m in state["statutes"]["mapped"]:
        q = f"{m['label']} " + " ".join(e["element"] for e in m["element_mapping"][:3])
        kw = dict(jurisdiction=state.get("jurisdiction") or case.jurisdiction, as_of=as_of, offence=m["offence_key"], instrument_types=["judgment"], top_k=3)
        similar = search_legal(ctx.db, q, stance=mine, **kw) if mine else search_legal(ctx.db, q, **kw)
        contrary = search_legal(ctx.db, q, stance=OPPOSITE[mine], **kw) if mine else {"hits": [], "coverage_gaps": ["Perspective is neutral: all retrieved judgments are listed under 'similar'; choose prosecution/defence to isolate contrary authority."]}
        out.append({"offence_key": m["offence_key"], "similar": [h["citation"] for h in similar["hits"]], "contrary": [h["citation"] for h in contrary["hits"]],
                    "coverage_gaps": similar["coverage_gaps"] + contrary["coverage_gaps"]})
    return {"precedents": {"perspective": persp, "per_offence": out}}


def punishment_compensation(state: WorkflowState, ctx: Ctx) -> dict:
    case = ctx.db.get(Case, ctx.run.case_id)
    as_of = date.fromisoformat(state["as_of"]) if state.get("as_of") else None
    pun = []
    for m in state["statutes"]["mapped"]:
        stmts = []
        for p in m["supporting_provisions"]:
            mm = re.search(r"(Punishment[^.]*(?:\.[^.]*)?)", p["excerpt"])
            if mm:
                stmts.append({"statement": mm.group(1).strip(), "citation": p})
        pun.append({"offence_key": m["offence_key"], "label": m["label"], "statutory_punishment": stmts,
                    "status": "from_cited_source" if stmts else "NOT_VERIFIED — no source in the knowledge base; consult the authoritative text"})
    comp = search_legal(ctx.db, "victim compensation scheme interim compensation eligibility", jurisdiction=state.get("jurisdiction") or case.jurisdiction, as_of=as_of, top_k=3)
    return {"punishment": {"per_offence": pun, "victim_compensation": [h["citation"] for h in comp["hits"]], "compensation_gaps": comp["coverage_gaps"],
                           "note": "Punishment ranges and compensation are reported ONLY from retrieved sources, never from model memory."}}


def citation_verification(state: WorkflowState, ctx: Ctx) -> dict:
    as_of = date.fromisoformat(state["as_of"]) if state.get("as_of") else None
    cites = []
    for m in state["statutes"]["mapped"]:
        cites += m["supporting_provisions"]
    for p in state["precedents"]["per_offence"]:
        cites += p["similar"] + p["contrary"]
    for p in state["punishment"]["per_offence"]:
        cites += [s["citation"] for s in p["statutory_punishment"]]
    cites += state["punishment"]["victim_compensation"]
    uniq = {c["chunk_id"]: c for c in cites}
    verdicts = [verify_citation(ctx.db, c, as_of=as_of) for c in uniq.values()]
    failed = [v for v in verdicts if v["verdict"] == "failed"]
    warn = [v for v in verdicts if v["verdict"] not in ("verified", "failed")]
    flags = guardrails.scan_structure({k: state[k] for k in ("statutes", "evidence_plan", "precedents", "punishment")})
    if flags:
        raise AgentValidationError(f"output guardrail triggered: {flags}")
    return {"citation_report": {"verdicts": verdicts, "failed": len(failed), "warnings": len(warn), "total": len(verdicts), "uncited_authority_mentions": [],
                                "status": "fail" if failed else ("pass_with_warnings" if warn or not verdicts else "pass")}}


def finalize(state: WorkflowState, ctx: Ctx) -> dict:
    case = ctx.db.get(Case, ctx.run.case_id)
    inc, cl, st, ev, pr, pu, cr = (state[k] for k in ("incident", "classification", "statutes", "evidence_plan", "precedents", "punishment", "citation_report"))
    synthetic = any(p["is_synthetic"] for m in st["mapped"] for p in m["supporting_provisions"]) or any(c["is_synthetic"] for o in pr["per_offence"] for c in o["similar"] + o["contrary"])
    S = []
    S.append(("Incident summary (as described — unverified)", [f"- {f['text']}" for f in inc["facts"][:12]] + [""] + [f"- To confirm: {x}" for x in inc["facts_to_confirm"]]))
    S.append(("Candidate offences and statutory provisions", [cl["note"], ""] + [f"- **{m['label']}** — {m['reference_candidate']} — *status:* `{m['verification_status']}`" for m in st["mapped"]] or ["- No candidate offence identified from the description."]))
    el = []
    for m in st["mapped"]:
        el += [f"### {m['label']}", "| Element | Status | Matched terms |", "|---|---|---|"] + [f"| {e['element']} | {e['status']} | {', '.join(e['matched_terms'])} |" for e in m["element_mapping"]] + [""]
        el += [f"- Source: {cite_line(p)}" for p in m["supporting_provisions"]] + [""]
    S.append(("Statutory element mapping", el or ["- None"]))
    S.append(("Evidence checklist and gaps", sum([[f"### {p['label']}"] + [f"- [{r['status'].upper()}] {r['item']}" for r in p["checklist"]] + [""] for p in ev["per_offence"]], []) or ["- None"]))
    S.append(("Similar judgments", sum([[f"- {cite_line(c)}" for c in o["similar"]] for o in pr["per_offence"]], []) or ["- None retrieved"]))
    S.append(("Contrary judgments", sum([[f"- {cite_line(c)}" for c in o["contrary"]] for o in pr["per_offence"]], []) or ["- None retrieved"]))
    pl = []
    for p in pu["per_offence"]:
        pl += [f"### {p['label']}"] + ([f"- {s['statement']} — {cite_line(s['citation'])}" for s in p["statutory_punishment"]] or [f"- {p['status']}"])
    pl += ["### Victim compensation"] + ([f"- {cite_line(c)}" for c in pu["victim_compensation"]] or ["- NOT VERIFIED — no source found"])
    S.append(("Punishment and victim compensation (from cited sources only)", pl))
    S.append(("Citation verification", [f"Status: **{cr['status']}** — {cr['total']} citations, {cr['failed']} failed, {cr['warnings']} warnings"]))
    S.append(("Limitations", ["- This report does not predict guilt, conviction or acquittal.", "- Candidate provisions are not verified law until supported by authoritative, human-verified sources.", "- Every item requires review by a qualified advocate."]))
    md = render_markdown(f"DandanAI Criminal Intelligence Report — {case.title}", S, mode=ctx.run.mode, status="draft", synthetic=synthetic, meta={"Generated": date.today().isoformat(), "Perspective": pr["perspective"]})
    rep = Report(org_id=ctx.run.org_id, case_id=case.id, run_id=ctx.run.id, kind="criminal_intelligence", title=f"Criminal intelligence — {case.title}",
                 content={"incident": inc, "classification": cl, "statutes": st, "evidence_plan": ev, "precedents": pr, "punishment": pu, "citation_report": cr},
                 markdown=md, status="draft", mode=ctx.run.mode, created_by=ctx.run.requested_by)
    ctx.db.add(rep)
    ctx.db.flush()
    ctx.run.report_id = rep.id
    return {"report": {"id": str(rep.id)}, "status": "awaiting_review"}


def build_graph(ctx: Ctx):
    g = StateGraph(WorkflowState)
    spec = [("incident_analysis", incident_analysis, lambda u: f"{len(u['incident']['facts'])} facts extracted; {len(u['incident']['facts_to_confirm'])} to confirm"),
            ("crime_classification", crime_classification, lambda u: f"{len(u['classification']['candidates'])} candidate offences (unverified)"),
            ("statute_mapping", statute_mapping, lambda u: f"{len(u['statutes']['mapped'])} candidates mapped to provisions/elements"),
            ("evidence_planner", evidence_planner, lambda u: "evidence checklists and gaps prepared"),
            ("precedent_research", precedent_research, lambda u: "similar and contrary judgments retrieved"),
            ("punishment_compensation", punishment_compensation, lambda u: "punishment/compensation sourced from retrieved text only"),
            ("citation_verification", citation_verification, lambda u: f"citations {u['citation_report']['status']}"),
            ("finalize", finalize, lambda u: "report drafted; awaiting human approval")]
    for name, fn, summ in spec:
        g.add_node(name, make_node(ctx, name if name != "finalize" else "human_review_gate", fn, summ))
    g.set_entry_point("incident_analysis")
    # explicit routing: no candidate offence -> skip straight to a (empty-result) report after a coverage note
    def after_class(state: WorkflowState) -> str:
        return "statute_mapping"
    for a, b in zip([s[0] for s in spec], [s[0] for s in spec][1:]):
        g.add_edge(a, b)
    g.add_edge("finalize", END)
    return g.compile()
