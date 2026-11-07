"""Legal RAG: chunking, hybrid retrieval (BM25 + vector, RRF fusion), jurisdiction/temporal filters, reranking,
citation objects, and citation verification."""
from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentChunk, LegalChunk, LegalInstrument
from app.services.jurisdictions import applicable
from app.services.providers import get_embedder, stem, tokenize


# ---------------------------------------------------------------- chunking
def chunk_text(pages: list[tuple[int, str]], size: int = 900, overlap: int = 150) -> list[dict]:
    out = []
    for pno, txt in pages:
        txt = txt.strip()
        if not txt:
            continue
        # keep sections intact: split on section-like headings first
        parts = re.split(r"\n(?=\s*(?:Section|Rule|Article|Clause|TS-\d+|Para|Chapter)\s*\d*)", txt) if re.search(r"\n\s*(Section|Rule|Article|Clause|Para)\s", txt) else [txt]
        for part in parts:
            part = part.strip()
            if len(part) <= size:
                out.append({"page": pno, "text": part})
                continue
            i = 0
            while i < len(part):
                out.append({"page": pno, "text": part[i:i + size]})
                i += size - overlap
    return [c for c in out if c["text"]]


def embed_texts(texts: list[str]) -> list[list[float]]:
    emb = get_embedder()
    out = []
    for i in range(0, len(texts), 64):
        out += emb.embed(texts[i:i + 64])
    return out


# ---------------------------------------------------------------- scoring
class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avg = (sum(len(d) for d in docs) / len(docs)) if docs else 0.0
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, q: list[str], i: int) -> float:
        d = self.docs[i]
        tf = Counter(d)
        s = 0.0
        for t in q:
            if t in tf:
                s += self.idf.get(t, 0) * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * len(d) / (self.avg or 1)))
        return s


VEC_STRONG, VEC_WEAK = 0.35, 0.10


def _vec_ok(vec: float, bm: float) -> bool:
    """A vector hit counts if strongly similar, or weakly similar AND lexically corroborated (suppresses embedding noise)."""
    return vec >= VEC_STRONG or (vec >= VEC_WEAK and bm > 0)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class Reranker:
    """Reranking interface. Default = lexical title/section boost. Swap for a cross-encoder in production."""

    def rerank(self, query: str, hits: list[dict]) -> list[dict]:
        q = {stem(t) for t in tokenize(query)}
        for h in hits:
            head = {stem(t) for t in tokenize((h["citation"].get("title") or "") + " " + (h["citation"].get("section") or ""))}
            h["score"] = h["score"] + 0.002 * len(q & head)
        return sorted(hits, key=lambda x: -x["score"])


def get_reranker() -> Reranker:
    return Reranker()


def _rrf(rank_lists: list[list[int]], k: int = 60) -> dict[int, float]:
    s: dict[int, float] = {}
    for rl in rank_lists:
        for r, idx in enumerate(rl):
            s[idx] = s.get(idx, 0) + 1.0 / (k + r + 1)
    return s


def _valid_on(inst: LegalInstrument, as_of: date | None, include_historical: bool) -> bool:
    """Temporal applicability. With an explicit as_of date, commencement/repeal dates are enforced strictly.
    Without it ("current law"), repealed instruments are excluded; synthetic 2099 test dates are not date-checked."""
    if include_historical:
        return True
    if as_of is None:
        if inst.status == "repealed":
            return False
        if inst.is_synthetic:
            return True
        d = date.today()
    else:
        d = as_of
    if inst.effective_from and inst.effective_from > d:
        return False
    if inst.effective_to and inst.effective_to <= d:
        return False
    return True


def citation_for(chunk: LegalChunk, inst: LegalInstrument) -> dict:
    return {"chunk_id": str(chunk.id), "instrument_id": str(inst.id), "title": inst.title, "authority_class": inst.authority_class,
            "instrument_type": inst.instrument_type, "section": chunk.section, "pinpoint": chunk.section or (f"p. {chunk.page}" if chunk.page else None),
            "court": inst.court, "citation": inst.citation, "jurisdiction": inst.jurisdiction, "date": inst.instrument_date.isoformat() if inst.instrument_date else None,
            "status": inst.status, "source_url": inst.source_url, "is_synthetic": inst.is_synthetic, "verification_status": inst.verification_status,
            "stance": (inst.tags or {}).get("stance"), "offences": (inst.tags or {}).get("offences", []), "excerpt": chunk.text[:600]}


def search_legal(db: Session, query: str, *, jurisdiction: str | None = None, as_of: date | None = None, instrument_types: list[str] | None = None,
                 authority: str | None = None, offence: str | None = None, stance: str | None = None, top_k: int = 6,
                 include_historical: bool = False) -> dict:
    """Hybrid retrieval over the legal corpus with jurisdiction + temporal filters. Returns hits, coverage and confidence."""
    juris = applicable(jurisdiction)
    stmt = select(LegalChunk, LegalInstrument).join(LegalInstrument, LegalInstrument.id == LegalChunk.instrument_id).where(LegalInstrument.jurisdiction.in_(juris))
    if instrument_types:
        stmt = stmt.where(LegalInstrument.instrument_type.in_(instrument_types))
    if authority:
        stmt = stmt.where(LegalInstrument.authority_class == authority)
    rows = [(c, i) for c, i in db.execute(stmt).all() if _valid_on(i, as_of, include_historical)]
    if offence:
        rows = [(c, i) for c, i in rows if offence in ((i.tags or {}).get("offences") or [])]
    if stance:
        rows = [(c, i) for c, i in rows if (i.tags or {}).get("stance") == stance]
    return _rank(rows, query, top_k, juris, as_of)


def _rank(rows, query: str, top_k: int, juris: list[str], as_of) -> dict:
    qtok = [stem(t) for t in tokenize(query)]
    if not rows or not qtok:
        return _result([], query, juris, as_of, 0)
    docs = [[stem(t) for t in tokenize(c.text + " " + (c.section or "") + " " + i.title + " " + " ".join((i.tags or {}).get("topics", [])))] for c, i in rows]
    bm = BM25(docs)
    bm_scores = [bm.score(qtok, k) for k in range(len(rows))]
    qv = get_embedder().embed([query])[0]
    vec_scores = [cosine(qv, c.embedding) if c.embedding else 0.0 for c, _ in rows]
    bm_rank = [i for i in sorted(range(len(rows)), key=lambda k: -bm_scores[k]) if bm_scores[i] > 0]
    vec_rank = [i for i in sorted(range(len(rows)), key=lambda k: -vec_scores[k]) if _vec_ok(vec_scores[i], bm_scores[i])]
    fused = _rrf([bm_rank, vec_rank])
    hits = []
    for idx, sc in sorted(fused.items(), key=lambda x: -x[1])[: top_k * 2]:
        c, i = rows[idx]
        hits.append({"score": sc, "bm25": round(bm_scores[idx], 3), "vector": round(vec_scores[idx], 3), "citation": citation_for(c, i)})
    hits = get_reranker().rerank(query, hits)[:top_k]
    return _result(hits, query, juris, as_of, len(rows))


def _result(hits, query, juris, as_of, candidates) -> dict:
    synth_only = bool(hits) and all(h["citation"]["is_synthetic"] for h in hits)
    unverified = bool(hits) and not any(h["citation"]["verification_status"] == "human_verified" for h in hits)
    prim = sum(1 for h in hits if h["citation"]["authority_class"] == "primary")
    gap = []
    if not hits:
        gap.append("No supporting source found in the knowledge base for this query and jurisdiction/date filter.")
    if hits and synth_only:
        gap.append("All retrieved sources are SYNTHETIC test data, not real law.")
    if hits and unverified and not synth_only:
        gap.append("Retrieved sources are not yet human-verified.")
    if hits and prim == 0:
        gap.append("No primary legal source among the results (secondary sources only).")
    if not hits:
        conf = "none"
    elif synth_only or unverified or prim == 0:
        conf = "low"
    else:
        conf = "medium" if len(hits) < 3 else "high"
    return {"query": query, "jurisdictions_searched": juris, "as_of": as_of.isoformat() if as_of else None, "candidates_considered": candidates,
            "hits": hits, "coverage_gaps": gap, "confidence": conf,
            "confidence_note": "Categorical retrieval-support indicator, not a probability of legal correctness.",
            "sufficient_support": bool(hits) and not synth_only}


def search_case_docs(db: Session, query: str, case_ids: list[uuid.UUID], org_id: uuid.UUID, top_k: int = 5) -> list[dict]:
    """Tenant-isolated retrieval over uploaded case documents: only chunks of cases the caller can access."""
    if not case_ids:
        return []
    rows = db.scalars(select(DocumentChunk).where(DocumentChunk.case_id.in_(case_ids), DocumentChunk.org_id == org_id)).all()
    qtok = [stem(t) for t in tokenize(query)]
    if not rows or not qtok:
        return []
    bm = BM25([[stem(t) for t in tokenize(c.text)] for c in rows])
    qv = get_embedder().embed([query])[0]
    bs = [bm.score(qtok, i) for i in range(len(rows))]
    vs = [cosine(qv, c.embedding) if c.embedding else 0.0 for c in rows]
    fused = _rrf([[i for i in sorted(range(len(rows)), key=lambda k: -bs[k]) if bs[i] > 0], [i for i in sorted(range(len(rows)), key=lambda k: -vs[k]) if _vec_ok(vs[i], bs[i])]])
    return [{"chunk_id": str(rows[i].id), "document_id": str(rows[i].document_id), "case_id": str(rows[i].case_id), "page": rows[i].page,
             "text": rows[i].text[:500], "score": round(s, 4)} for i, s in sorted(fused.items(), key=lambda x: -x[1])[:top_k]]


# ---------------------------------------------------------------- citation verification
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def verify_citation(db: Session, cite: dict, *, quote: str | None = None, as_of: date | None = None) -> dict:
    """Checks: chunk exists; quoted text appears verbatim; instrument in force on the date; authority-verification status."""
    res = {"chunk_id": cite.get("chunk_id"), "title": cite.get("title"), "checks": {}, "verdict": "verified"}
    try:
        ch = db.get(LegalChunk, uuid.UUID(str(cite.get("chunk_id"))))
    except ValueError:
        ch = None
    if not ch:
        res["checks"]["exists"] = False
        res["verdict"] = "failed"
        return res
    inst = db.get(LegalInstrument, ch.instrument_id)
    res["checks"]["exists"] = True
    res["checks"]["metadata_matches"] = (inst.title == cite.get("title")) and (not cite.get("section") or cite.get("section") == ch.section)
    if quote is not None:
        res["checks"]["quote_verbatim"] = _norm(quote) in _norm(ch.text)
    d = as_of or date.today()
    res["checks"]["in_force_on_date"] = inst.status != "repealed" and not (inst.effective_to and inst.effective_to <= d and not inst.is_synthetic)
    res["checks"]["human_verified_source"] = inst.verification_status == "human_verified"
    res["checks"]["real_source"] = not inst.is_synthetic
    if not (res["checks"]["exists"] and res["checks"]["metadata_matches"]) or res["checks"].get("quote_verbatim") is False:
        res["verdict"] = "failed"
    elif not res["checks"]["in_force_on_date"]:
        res["verdict"] = "warning_not_in_force"
    elif not res["checks"]["real_source"]:
        res["verdict"] = "synthetic_test_source"
    elif not res["checks"]["human_verified_source"]:
        res["verdict"] = "unverified_source"
    return res


_AUTH_MENTION = re.compile(r"\b(?:Section|Sec\.?|Article|Rule)\s+\d+[A-Za-z]?(?:\(\d+\))?(?:\s+of\s+(?:the\s+)?[A-Z][A-Za-z&,' -]{2,60}?(?:Act|Code|Rules|Sanhita)(?:,?\s*\d{4})?)?")


def find_uncited_authorities(text: str, cited_titles: list[str]) -> list[str]:
    """Flags statute/section mentions in free text that are not backed by any supplied citation (possible fabrication)."""
    bad = []
    low_titles = " ".join(cited_titles).lower()
    for m in _AUTH_MENTION.finditer(text or ""):
        frag = m.group(0)
        mm = re.search(r"of\s+(?:the\s+)?(.+)$", frag)
        name = (mm.group(1) if mm else "").lower().strip(" ,")
        if name and name not in low_titles:
            bad.append(frag)
    return bad
