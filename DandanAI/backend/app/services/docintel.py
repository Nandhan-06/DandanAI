"""Deterministic document intelligence: classification, entity/date/amount/clause extraction, summary, comparison.

Everything extracted is `explicit` (found in the text, with page provenance). Interpretations (risks, missing
information) are `ai_inferred` and labelled so the UI can distinguish them."""
import difflib
import re
from datetime import date

DOC_TYPES = ["rental_agreement", "employment_agreement", "property_agreement", "legal_notice", "judgment", "complaint",
             "evidence", "other"]
_KW = {
    "rental_agreement": ["landlord", "tenant", "lessor", "lessee", "monthly rent", "security deposit", "lock-in", "leave and licence"],
    "employment_agreement": ["employer", "employee", "salary", "probation", "designation", "notice period", "non-compete", "ctc"],
    "property_agreement": ["sale deed", "vendor", "purchaser", "vendee", "agreement to sell", "title", "possession", "conveyance", "earnest money"],
    "legal_notice": ["legal notice", "hereby call upon", "notice under", "failing which", "without prejudice", "my client"],
    "judgment": ["petitioner", "respondent", "appellant", "judgment", "hon'ble", "court held", "order", "bench"],
    "complaint": ["complaint", "complainant", "i state that", "grievance", "request you to take action", "fir", "cheated"],
    "evidence": ["receipt", "invoice", "screenshot", "bank statement", "whatsapp", "exhibit", "photograph"],
}
CLAUSE_HEADS = ["Parties", "Term", "Duration", "Rent", "Salary", "Compensation", "Security Deposit", "Deposit", "Payment",
                "Lock-in", "Notice", "Termination", "Renewal", "Confidentiality", "Non-compete", "Indemnity", "Governing Law",
                "Jurisdiction", "Arbitration", "Maintenance", "Repairs", "Probation", "Leave", "Penalty", "Default", "Dispute"]
REQUIRED = {
    "rental_agreement": ["party", "amount", "date", "duration", "termination", "deposit", "jurisdiction", "signature"],
    "employment_agreement": ["party", "amount", "date", "duration", "termination", "notice", "jurisdiction", "signature"],
    "property_agreement": ["party", "amount", "date", "jurisdiction", "signature", "possession"],
    "legal_notice": ["party", "date", "deadline"],
    "complaint": ["party", "date"],
}
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_DATE_RES = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"), lambda m: (int(m[3]), int(m[2]), int(m[1]))),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?),?\s+(\d{4})\b", re.I),
     lambda m: (int(m[3]), _MONTHS.index(m[2][:3].lower()) + 1, int(m[1]))),
]
_AMOUNT = re.compile(r"(?:Rs\.?|INR|₹)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:lakhs?|crores?|thousand))?", re.I)
_LEGAL_REF = re.compile(r"(?:Section|Sec\.?|S\.)\s?\d+[A-Za-z]?(?:\(\d+\))?(?:\s+of\s+(?:the\s+)?[A-Z][A-Za-z&,' -]{2,60}?(?:Act|Code|Rules|Sanhita|Regulations)(?:,?\s*\d{4})?)?"
                        r"|Article\s?\d+[A-Z]?(?:\(\d+\))?(?:\s+of the Constitution)?|[A-Z][A-Za-z&' -]{3,50}\s(?:Act|Code),?\s\d{4}")
_DURATION = re.compile(r"(?:for a (?:period|term) of|valid for|period of|term of)\s+(\d+|[a-z]+)\s*\(?\d*\)?\s*(months?|years?|days?)|\b(\d+)[- ](month|year)s?\b", re.I)
_PARTY_BETWEEN = re.compile(r"between\s+(.{3,120}?)\s+(?:\(|and\s)", re.I)
_PARTY_ROLE = re.compile(r"((?:(?:M/s|Mr|Mrs|Ms|Shri|Smt|Dr)\.?\s+)?[A-Z][\w&'-]+(?:\s+[A-Z][\w&'-]+){0,3})\s*\(\s*(?:hereinafter\s+)?(?:referred to as\s+)?(?:the\s+)?[“\"']?(Landlord|Tenant|Lessor|Lessee|Employer|Employee|Vendor|Purchaser|Seller|Buyer|Licensor|Licensee|Complainant|Accused|Petitioner|Respondent)[”\"']?\s*\)", re.I)
_TITLED = re.compile(r"\b(?:Mr|Mrs|Ms|Shri|Smt|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}")
_S = r"(?:[^.\n]|(?<=Rs)\.|(?<=Mr)\.|(?<=Ms)\.|(?<=Mrs)\.|(?<=Dr)\.)*"
_DEADLINE = re.compile(_S + r"\b(?:within\s+\d+\s+days|on or before|not later than|deadline|due (?:date|on)|by\s+\d{1,2}[/-]\d{1,2}[/-]\d{4})" + _S, re.I)
_OBLIG = re.compile(_S + r"\b(?:shall|must|agrees to|undertakes to|is liable to|is obliged to)\b" + _S, re.I)
_WORDNUM = {"one": 1, "two": 2, "three": 3, "six": 6, "eleven": 11, "twelve": 12, "twenty-four": 24}


def classify(text: str) -> tuple[str, dict]:
    low = text.lower()
    scores = {k: sum(low.count(w) for w in ws) for k, ws in _KW.items()}
    best = max(scores, key=scores.get)
    return (best if scores[best] >= 2 else "other"), scores


def parse_date(txt: str) -> date | None:
    for rx, f in _DATE_RES:
        m = rx.search(txt)
        if m:
            try:
                y, mo, d = f(m)
                return date(y, mo, d)
            except ValueError:
                return None
    return None


def _items(pages, rx, kind, label=None, group=0, limit=60):
    out, seen = [], set()
    for pno, ptxt in pages:
        for m in rx.finditer(ptxt):
            v = " ".join(m.group(group).split())
            if (kind, v.lower()) in seen or not v:
                continue
            seen.add((kind, v.lower()))
            out.append({"kind": kind, "label": label, "value": v[:400], "page": pno, "origin": "explicit", "confidence": 1.0})
            if len(out) >= limit:
                return out
    return out


def analyse(pages: list[tuple[int, str]], doc_type_hint: str | None = None) -> dict:
    """pages = [(page_no, text)]. Returns doc_type, items (extractions) and a structured summary."""
    full = "\n".join(t for _, t in pages)
    cls, scores = classify(full)
    doc_type = doc_type_hint if doc_type_hint and doc_type_hint != "other" else cls
    items: list[dict] = []

    for pno, ptxt in pages:
        for m in _PARTY_ROLE.finditer(ptxt):
            items.append({"kind": "party", "label": m.group(2).title(), "value": " ".join(m.group(1).split()), "page": pno, "origin": "explicit", "confidence": 0.9})
        for m in _TITLED.finditer(ptxt):
            v = m.group(0)
            if not any(i["kind"] == "party" and v.lower() in i["value"].lower() for i in items):
                items.append({"kind": "party", "label": "Named person", "value": v, "page": pno, "origin": "explicit", "confidence": 0.6})
    seen = set()
    items = [i for i in items if not ((i["kind"], i["value"].lower()) in seen or seen.add((i["kind"], i["value"].lower())))]

    dates = []
    for pno, ptxt in pages:
        for rx, f in _DATE_RES:
            for m in rx.finditer(ptxt):
                try:
                    y, mo, d = f(m)
                    dt = date(y, mo, d)
                except ValueError:
                    continue
                ctx = ptxt[max(0, m.start() - 50): m.end() + 20].replace("\n", " ")
                dates.append({"kind": "date", "label": None, "value": dt.isoformat(), "page": pno, "origin": "explicit", "confidence": 1.0, "context": ctx})
    uniq = {(d["value"], d["page"]): d for d in dates}
    items += list(uniq.values())

    items += _items(pages, _AMOUNT, "amount")
    items += _items(pages, _LEGAL_REF, "legal_ref")
    items += _items(pages, _DEADLINE, "deadline", limit=20)
    items += _items(pages, _OBLIG, "obligation", limit=30)
    for pno, ptxt in pages:
        for m in _DURATION.finditer(ptxt):
            items.append({"kind": "duration", "label": "Agreement duration", "value": " ".join(m.group(0).split()), "page": pno, "origin": "explicit", "confidence": 0.9})
            break

    # clauses: paragraphs that start with a (numbered) heading naming a known clause topic
    for pno, ptxt in pages:
        for para in re.split(r"\n\s*\n|\n(?=\s*\d+[.)]\s)", ptxt):
            p = " ".join(para.split())
            m = re.match(r"^(?:Clause\s+)?(?:\d+(?:\.\d+)*[.)]?\s*)?([A-Za-z][A-Za-z -]{2,40}?)\s*[:.\-–]\s+(.{15,})", p)
            if m and any(h.lower() in m.group(1).lower() for h in CLAUSE_HEADS):
                items.append({"kind": "clause", "label": m.group(1).strip().title(), "value": m.group(2)[:600], "page": pno, "origin": "explicit", "confidence": 0.85})

    kinds = {i["kind"] for i in items}
    low = full.lower()
    present = {"party": "party" in kinds, "amount": "amount" in kinds, "date": "date" in kinds, "duration": "duration" in kinds,
               "termination": "terminat" in low, "deposit": "deposit" in low, "notice": "notice" in low,
               "jurisdiction": "jurisdiction" in low or "governing law" in low or "courts at" in low,
               "signature": any(w in low for w in ("signed", "signature", "witness", "in witness whereof")),
               "possession": "possession" in low, "deadline": "deadline" in kinds}
    missing = [r for r in REQUIRED.get(doc_type, []) if not present.get(r)]
    for r in missing:
        items.append({"kind": "missing", "label": "Missing information", "value": f"No {r.replace('_', ' ')} found in the text", "page": None,
                      "origin": "ai_inferred", "confidence": 0.7})
    risks = []
    if doc_type in REQUIRED and "termination" in missing:
        risks.append("No termination condition identified")
    if "jurisdiction" in missing:
        risks.append("No governing-law / jurisdiction clause identified")
    if any("lock-in" in (i.get("label") or "").lower() for i in items):
        risks.append("Lock-in clause present — review exit costs")
    for r in risks:
        items.append({"kind": "risk", "label": "Potential risk", "value": r, "page": None, "origin": "ai_inferred", "confidence": 0.6})

    def vals(k, n=20):
        return [{"value": i["value"], "label": i.get("label"), "page": i["page"]} for i in items if i["kind"] == k][:n]

    summary = {"document_type": doc_type, "classifier_scores": scores, "parties": vals("party"), "important_dates": vals("date"),
               "duration": vals("duration"), "financial_obligations": vals("amount"), "key_clauses": vals("clause", 30),
               "obligations": vals("obligation", 15), "legal_references": vals("legal_ref"), "deadlines": vals("deadline"),
               "potential_risks": [{"value": r, "origin": "ai_inferred"} for r in risks],
               "missing_information": [{"value": i["value"], "origin": "ai_inferred"} for i in items if i["kind"] == "missing"],
               "provenance_note": "Items with origin 'explicit' quote the document with page numbers; 'ai_inferred' items are heuristic interpretations."}
    return {"doc_type": doc_type, "items": items, "summary": summary}


def compare(a: dict, b: dict) -> dict:
    """a, b: {'name', 'items': [...]}. Clause-by-clause, financial, termination, missing clauses, inconsistencies."""
    def clauses(d):
        return {i["label"]: i for i in d["items"] if i["kind"] == "clause"}

    ca, cb = clauses(a), clauses(b)
    diffs, only_a, only_b = [], [], []
    for k in sorted(set(ca) | set(cb)):
        if k in ca and k in cb:
            ratio = difflib.SequenceMatcher(None, ca[k]["value"], cb[k]["value"]).ratio()
            if ratio < 0.98:
                diffs.append({"clause": k, "a": ca[k]["value"], "b": cb[k]["value"], "a_page": ca[k]["page"], "b_page": cb[k]["page"],
                              "similarity": round(ratio, 2), "origin": "explicit"})
        elif k in ca:
            only_a.append({"clause": k, "page": ca[k]["page"]})
        else:
            only_b.append({"clause": k, "page": cb[k]["page"]})

    def money(d):
        return sorted({i["value"] for i in d["items"] if i["kind"] == "amount"})

    ma, mb = money(a), money(b)
    term_a = [i["value"] for i in a["items"] if i["kind"] == "clause" and "terminat" in (i["label"] or "").lower()]
    term_b = [i["value"] for i in b["items"] if i["kind"] == "clause" and "terminat" in (i["label"] or "").lower()]
    incons = []
    pa = {i["value"].lower() for i in a["items"] if i["kind"] == "party"}
    pb = {i["value"].lower() for i in b["items"] if i["kind"] == "party"}
    if pa and pb and not (pa & pb):
        incons.append({"value": "The two documents share no common party name", "origin": "ai_inferred"})
    if term_a != term_b:
        incons.append({"value": "Termination conditions differ between the documents", "origin": "ai_inferred"})
    return {"documents": [a["name"], b["name"]], "clause_differences": diffs, "clauses_only_in_a": only_a, "clauses_only_in_b": only_b,
            "financial_terms": {"a": ma, "b": mb, "only_in_a": sorted(set(ma) - set(mb)), "only_in_b": sorted(set(mb) - set(ma))},
            "termination": {"a": term_a, "b": term_b, "different": term_a != term_b}, "potential_inconsistencies": incons,
            "note": "Clause differences are explicit text comparisons; inconsistencies are heuristic and need human review."}
