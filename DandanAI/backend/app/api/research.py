import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.util import to_dict
from app.core.config import get_settings
from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models import IngestionJob, LegalChunk, LegalInstrument, LegalSource, User
from app.services import guardrails
from app.services.audit import audit
from app.services.extraction import extract, sniff_ok
from app.services.jurisdictions import HIGH_COURTS, LAYERS, STATES, UTS
from app.services.rag import chunk_text, embed_texts, search_legal

router = APIRouter(prefix="/api/v1", tags=["legal-research"])
pro = require_roles("advocate", "admin")


class SearchIn(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    jurisdiction: str | None = None
    as_of: date | None = None
    instrument_types: list[str] | None = None
    authority: str | None = None
    include_historical: bool = False
    top_k: int = Field(6, ge=1, le=20)


@router.post("/research/search")
def research(body: SearchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q, flags = guardrails.clean_input(body.query, max_chars=2000)
    res = search_legal(db, q, jurisdiction=body.jurisdiction, as_of=body.as_of, instrument_types=body.instrument_types, authority=body.authority,
                       top_k=body.top_k, include_historical=body.include_historical)
    audit(db, user, "research.search", "legal", None, {"hits": len(res["hits"])})
    db.commit()
    return {**res, "input_flags": flags, "classification_note": "Primary = legislation/judgments; secondary = commentary; AI-generated analysis is never returned here — only retrieved sources.",
            "disclaimer": guardrails.DISCLAIMER}


@router.get("/instruments")
def instruments(q: str | None = None, instrument_type: str | None = None, jurisdiction: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(LegalInstrument)
    if q:
        stmt = stmt.where(LegalInstrument.title.ilike(f"%{q}%"))
    if instrument_type:
        stmt = stmt.where(LegalInstrument.instrument_type == instrument_type)
    if jurisdiction:
        stmt = stmt.where(LegalInstrument.jurisdiction == jurisdiction)
    return [to_dict(i) for i in db.scalars(stmt.order_by(LegalInstrument.created_at.desc()).limit(200)).all()]


@router.get("/instruments/{iid}")
def instrument(iid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    i = db.get(LegalInstrument, iid)
    if not i:
        raise HTTPException(404, "Instrument not found")
    chunks = db.scalars(select(LegalChunk).where(LegalChunk.instrument_id == i.id).order_by(LegalChunk.chunk_no)).all()
    return {**to_dict(i), "chunks": [{"id": str(c.id), "section": c.section, "page": c.page, "text": c.text} for c in chunks]}


class VerifyIn(BaseModel):
    note: str | None = None


@router.post("/instruments/{iid}/verify")
def verify_instrument(iid: uuid.UUID, body: VerifyIn, user: User = Depends(pro), db: Session = Depends(get_db)):
    i = db.get(LegalInstrument, iid)
    if not i:
        raise HTTPException(404, "Instrument not found")
    if i.is_synthetic:
        raise HTTPException(422, "Synthetic test data can never be marked human-verified")
    i.verification_status, i.verified_by, i.verified_at = "human_verified", user.id, datetime.now(timezone.utc)
    audit(db, user, "instrument.verify", "instrument", i.id, {"note": body.note})
    db.commit()
    return to_dict(i)


@router.post("/instruments/ingest", status_code=201)
async def ingest(file: UploadFile = File(...), title: str = Form(...), instrument_type: str = Form("act"), jurisdiction: str = Form("India"),
                 source_url: str | None = Form(None), instrument_date: date | None = Form(None), effective_from: date | None = Form(None),
                 effective_to: date | None = Form(None), court: str | None = Form(None), citation: str | None = Form(None),
                 source_id: uuid.UUID | None = Form(None), authority_class: str = Form("primary"),
                 user: User = Depends(pro), db: Session = Depends(get_db)):
    """Manual ingestion of a legal instrument the operator is permitted to use (PDF/DOCX). Starts as 'unverified'."""
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    if ext not in (".pdf", ".docx") or not sniff_ok(ext, data):
        raise HTTPException(415, "Only PDF or DOCX instruments are accepted")
    ex = extract(ext, data)
    if ex.status != "extracted":
        raise HTTPException(422, f"Could not extract text: {ex.error}")
    inst = LegalInstrument(source_id=source_id, title=title[:400], instrument_type=instrument_type, authority_class=authority_class, jurisdiction=jurisdiction,
                           court=court, citation=citation, source_url=source_url, instrument_date=instrument_date, effective_from=effective_from or instrument_date,
                           effective_to=effective_to, verification_status="unverified", tags={})
    db.add(inst)
    db.flush()
    ch = chunk_text([(p.no, p.text) for p in ex.pages])
    for n, (c, e) in enumerate(zip(ch, embed_texts([c["text"] for c in ch]))):
        db.add(LegalChunk(instrument_id=inst.id, chunk_no=n, page=c["page"], section=(c["text"].split(".")[0][:60] if c["text"][:7].lower().startswith(("section", "rule", "article")) else None), text=c["text"], embedding=e))
    if source_id and (src := db.get(LegalSource, source_id)):
        src.ingestion_status = "partial"
    db.add(IngestionJob(source_id=source_id, kind="manual_upload", status="completed", instruments_added=1, chunks_added=len(ch), started_by=user.id))
    audit(db, user, "instrument.ingest", "instrument", inst.id, {"chunks": len(ch)})
    db.commit()
    return {**to_dict(inst), "chunks_added": len(ch)}


class AmendIn(BaseModel):
    description: str
    effective_date: date | None = None
    new_status: str | None = None  # in_force|amended|repealed|historical
    effective_to: date | None = None


@router.post("/instruments/{iid}/amendments")
def add_amendment(iid: uuid.UUID, body: AmendIn, user: User = Depends(pro), db: Session = Depends(get_db)):
    i = db.get(LegalInstrument, iid)
    if not i:
        raise HTTPException(404, "Instrument not found")
    i.amendments = [*(i.amendments or []), {"description": body.description, "effective_date": body.effective_date.isoformat() if body.effective_date else None,
                                            "recorded_by": str(user.id)}]
    if body.new_status:
        i.status = body.new_status
    if body.effective_to:
        i.effective_to = body.effective_to
    audit(db, user, "instrument.amend", "instrument", i.id, body.model_dump(mode="json"))
    db.commit()
    return to_dict(i)


# ------------------------------------------------------------------ source registry & coverage dashboard
@router.get("/sources")
def sources(layer: str | None = None, jurisdiction: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(LegalSource)
    if layer:
        stmt = stmt.where(LegalSource.layer == layer)
    if jurisdiction:
        stmt = stmt.where(LegalSource.jurisdiction == jurisdiction)
    return [to_dict(s) for s in db.scalars(stmt.order_by(LegalSource.layer, LegalSource.jurisdiction, LegalSource.name)).all()]


class SourcePatch(BaseModel):
    url: str | None = None
    access_method: str | None = None
    access_status: str | None = None
    licence_note: str | None = None
    ingestion_status: str | None = None


@router.patch("/sources/{sid}")
def patch_source(sid: uuid.UUID, body: SourcePatch, user: User = Depends(require_roles("admin", "advocate")), db: Session = Depends(get_db)):
    s = db.get(LegalSource, sid)
    if not s:
        raise HTTPException(404, "Source not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    audit(db, user, "source.update", "source", s.id, body.model_dump(exclude_none=True))
    db.commit()
    return to_dict(s)


@router.post("/sources/{sid}/check")
def monitor_source(sid: uuid.UUID, user: User = Depends(pro), db: Session = Depends(get_db)):
    """Update-monitoring hook. External fetches are disabled unless ALLOW_EXTERNAL_FETCH=true AND the source access_status is 'permitted'."""
    s = db.get(LegalSource, sid)
    if not s:
        raise HTTPException(404, "Source not found")
    s.last_checked_at = datetime.now(timezone.utc)
    if not (get_settings().allow_external_fetch and s.access_status == "permitted" and s.url):
        msg = "No network check performed: external fetch disabled or source access not marked 'permitted'. Recorded as a manual check."
    else:
        msg = "External monitoring is enabled but no adapter is implemented for this source yet (manual ingestion required)."
    db.add(IngestionJob(source_id=s.id, kind="monitor", status="skipped", message=msg, started_by=user.id))
    db.commit()
    return {"source_id": str(s.id), "message": msg, "last_checked_at": s.last_checked_at.isoformat()}


@router.get("/ingestion-jobs")
def jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [to_dict(j) for j in db.scalars(select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(100)).all()]


@router.get("/coverage")
def coverage(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Coverage dashboard. Counts what is actually stored; it never asserts complete coverage."""
    inst = db.execute(select(LegalInstrument.jurisdiction, LegalInstrument.is_synthetic, LegalInstrument.verification_status, func.count()).group_by(
        LegalInstrument.jurisdiction, LegalInstrument.is_synthetic, LegalInstrument.verification_status)).all()
    src = db.execute(select(LegalSource.layer, LegalSource.ingestion_status, LegalSource.is_synthetic, func.count()).group_by(LegalSource.layer, LegalSource.ingestion_status, LegalSource.is_synthetic)).all()
    layers = []
    for key, label in LAYERS:
        rows = [r for r in src if r[0] == key]
        layers.append({"layer": key, "label": label, "registered_sources": sum(r[3] for r in rows if not r[2]),
                       "sources_ingested_or_partial": sum(r[3] for r in rows if r[1] in ("partial", "complete") and not r[2]), "not_started": sum(r[3] for r in rows if r[1] == "not_started" and not r[2])})
    real = [r for r in inst if not r[1]]
    by_j = {}
    for j, synth, ver, n in inst:
        d = by_j.setdefault(j, {"real": 0, "synthetic": 0, "human_verified": 0})
        d["synthetic" if synth else "real"] += n
        if ver == "human_verified":
            d["human_verified"] += n
    return {"coverage_audit": "NOT PERFORMED — no verified nationwide coverage audit exists. Figures below are counts of what is stored, not claims of completeness.",
            "totals": {"instruments_real": sum(r[3] for r in real), "instruments_synthetic_test": sum(r[3] for r in inst if r[1]), "human_verified": sum(r[3] for r in real if r[2] == "human_verified")},
            "jurisdictions_expected": {"central": 1, "states": len(STATES), "union_territories": len(UTS), "high_courts": len(HIGH_COURTS)},
            "jurisdictions_with_real_instruments": sorted({r[0] for r in real}), "per_jurisdiction": by_j, "layers": layers,
            "states_without_real_instruments": [s for s in STATES + UTS if s not in {r[0] for r in real}]}
