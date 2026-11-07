"""Idempotent seeding: legal source registry (planning records, NOT coverage claims) + SYNTHETIC test corpus."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IngestionJob, LegalChunk, LegalInstrument, LegalSource
from app.services import corpus
from app.services.jurisdictions import HIGH_COURTS, STATES, UTS
from app.services.rag import embed_texts


def seed_sources(db: Session) -> int:
    have = {(s.name, s.jurisdiction) for s in db.scalars(select(LegalSource)).all()}
    new = []

    def add(name, layer, jur, url=None, note=None, method="manual"):
        if (name, jur) not in have:
            new.append(LegalSource(name=name, layer=layer, jurisdiction=jur, url=url, licence_note=note, access_method=method))

    for name, layer, jur, url, note in corpus.SOURCES:
        add(name, layer, jur, url, note)
    for st in STATES + UTS:
        add(f"State/UT legislation — {st}", "state_uts_legislation", st, None, "Registry placeholder. Identify the official portal and confirm terms of use.")
        add(f"Rules, notifications & circulars — {st}", "state_rules_notifications", st, None, "Registry placeholder.")
        add(f"Municipal bylaws & development regulations — {st}", "municipal_bylaws", st, None, "Registry placeholder.")
    for hc in HIGH_COURTS:
        add(f"High Court of {hc}", "high_courts", hc, None, "Registry placeholder. Confirm official site, bench list and terms.")
    for name, layer in [("Tribunals registry (NCLT/NCLAT/ITAT/NGT/CAT/…)", "tribunals"), ("Regulators registry (SEBI/RBI/TRAI/CCI/…)", "regulators"),
                        ("District & subordinate courts (via eCourts)", "district_courts"), ("Treaties & specialised instruments", "treaties_specialised"),
                        ("Development regulations (local notifications)", "development_regulations")]:
        add(name, layer, "India", None, "Registry placeholder.")
    db.add_all(new)
    db.commit()
    return len(new)


def seed_synthetic_corpus(db: Session) -> dict:
    have = {t for (t,) in db.execute(select(LegalInstrument.title)).all()}
    added_i = added_c = 0
    src = db.scalar(select(LegalSource).where(LegalSource.name == "Synthetic test corpus"))
    if not src:
        src = LegalSource(name="Synthetic test corpus", layer="constitution_central_acts", jurisdiction="India", access_method="manual", access_status="permitted",
                          ingestion_status="synthetic", is_synthetic=True, licence_note="Fictional test data generated for DandanAI. Not law.")
        db.add(src)
        db.flush()
    for d in corpus.INSTRUMENTS:
        if d["title"] in have:
            continue
        inst = LegalInstrument(source_id=src.id, title=d["title"], instrument_type=d["type"], authority_class=d.get("authority", "primary"), jurisdiction=d["jur"],
                               court=d.get("court"), citation=d.get("cite"), instrument_date=d["d"], effective_from=d.get("eff"), effective_to=d.get("eff_to"),
                               status=d.get("status", "in_force"), tags=d.get("tags"), verification_status="synthetic_test", is_synthetic=True,
                               source_url=None)
        db.add(inst)
        db.flush()
        texts = [t for _, t in d["chunks"]]
        embs = embed_texts(texts)
        for n, ((sec, txt), emb) in enumerate(zip(d["chunks"], embs)):
            db.add(LegalChunk(instrument_id=inst.id, chunk_no=n, section=sec, text=txt, embedding=emb))
            added_c += 1
        added_i += 1
    if added_i:
        db.add(IngestionJob(source_id=src.id, kind="seed", status="completed", instruments_added=added_i, chunks_added=added_c, message="Synthetic corpus"))
    src.ingestion_status = "synthetic"
    db.commit()
    return {"instruments": added_i, "chunks": added_c}
