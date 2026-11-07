"""Background document processing: extract -> pages -> intelligence -> chunks/embeddings -> suggested deadlines/timeline."""
import uuid
from datetime import date

from sqlalchemy import delete

from app.database import session_factory
from app.models import Document, DocumentChunk, DocumentPage, Extraction, Task, TimelineEvent
from app.services import docintel
from app.services.extraction import extract
from app.services.providers import get_llm, get_storage
from app.services.rag import chunk_text, embed_texts


def process_document(doc_id: uuid.UUID) -> None:
    db = session_factory()()
    try:
        doc = db.get(Document, doc_id)
        if not doc:
            return
        doc.processing_status = "processing"
        db.commit()
        data = get_storage().get(doc.storage_key)
        ext = "." + doc.filename.rsplit(".", 1)[-1].lower()
        ex = extract(ext, data)
        doc.processing_status, doc.processing_error, doc.page_count = ex.status, ex.error, len(ex.pages) or None
        db.execute(delete(DocumentPage).where(DocumentPage.document_id == doc.id))
        db.execute(delete(Extraction).where(Extraction.document_id == doc.id))
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        for p in ex.pages:
            db.add(DocumentPage(document_id=doc.id, page_no=p.no, text=p.text, ocr=p.ocr))
        doc.extracted_text = ex.text or None
        if ex.status == "extracted" and ex.text.strip():
            pages = [(p.no, p.text) for p in ex.pages]
            an = docintel.analyse(pages, doc.doc_type if doc.doc_type_source == "user" else None)
            if doc.doc_type_source != "user" or not doc.doc_type or doc.doc_type == "other":
                doc.doc_type, doc.doc_type_source = an["doc_type"], "classifier"
            for it in an["items"]:
                db.add(Extraction(document_id=doc.id, case_id=doc.case_id, kind=it["kind"], label=it.get("label"), value=it["value"], page=it.get("page"),
                                  locator="docx-body" if ext == ".docx" and it.get("page") else None, origin=it["origin"], confidence=it.get("confidence", 1.0)))
            llm = get_llm()
            an["summary"]["narrative"] = llm.complete("Summarise neutrally.", f"Summary of {doc.filename} ({doc.doc_type}): {len(an['items'])} extracted items.")
            an["summary"]["narrative_mode"] = "mock" if llm.is_mock else "live"
            doc.summary = an["summary"]
            ch = chunk_text(pages)
            embs = embed_texts([c["text"] for c in ch]) if ch else []
            for n, (c, e) in enumerate(zip(ch, embs)):
                db.add(DocumentChunk(org_id=doc.org_id, case_id=doc.case_id, document_id=doc.id, chunk_no=n, page=c["page"], text=c["text"], embedding=e))
            # suggested (unreviewed) deadlines and timeline events with provenance
            for it in an["items"]:
                if it["kind"] == "deadline":
                    db.add(Task(case_id=doc.case_id, title=f"[from {doc.filename} p.{it['page']}] {it['value'][:200]}", kind="deadline", source="extracted", reviewed=False,
                                due_date=docintel.parse_date(it["value"])))
            for it in [i for i in an["items"] if i["kind"] == "date"][:10]:
                db.add(TimelineEvent(case_id=doc.case_id, event_date=date.fromisoformat(it["value"]), title=f"Date in {doc.filename}", description=it.get("context"),
                                     document_id=doc.id, page=it["page"], source="extracted"))
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        doc = db.get(Document, doc_id)
        if doc:
            doc.processing_status, doc.processing_error = "failed", f"{type(e).__name__}: {e}"[:500]
            db.commit()
    finally:
        db.close()
