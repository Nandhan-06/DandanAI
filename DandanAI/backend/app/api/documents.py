import hashlib
import os
import re
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.util import to_dict
from app.core.config import get_settings
from app.database import get_db
from app.deps import CaseCtx, get_case_read, get_case_write
from app.models import Document, DocumentPage, Extraction
from app.services import docintel
from app.services.audit import audit
from app.services.docproc import process_document
from app.services.extraction import ALLOWED, sniff_ok
from app.services.providers import get_storage

router = APIRouter(prefix="/api/v1/cases/{case_id}/documents", tags=["documents"])
DOC_TYPES = set(docintel.DOC_TYPES) | {"auto"}


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(name))[:200] or "file"


def _doc(db: Session, case_id, document_id) -> Document:
    d = db.get(Document, document_id)
    if not d or d.case_id != case_id:  # a document must belong to the authorised case
        raise HTTPException(404, "Document not found")
    return d


@router.post("", status_code=201)
async def upload(bg: BackgroundTasks, file: UploadFile = File(...), doc_type: str = Form("auto"), is_synthetic: bool = Form(False),
                 replaces_document_id: uuid.UUID | None = Form(None), ctx: CaseCtx = Depends(get_case_write), db: Session = Depends(get_db)):
    s = get_settings()
    if doc_type not in DOC_TYPES:
        raise HTTPException(422, "Unknown doc_type")
    name = _safe_name(file.filename or "file")
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED:
        raise HTTPException(415, "Unsupported file type (PDF, DOCX, PNG, JPG only)")
    limit = s.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds {s.max_upload_mb} MB")
    if not data or not sniff_ok(ext, data):
        raise HTTPException(415, "File content does not match its extension")
    group, version = uuid.uuid4(), 1
    if replaces_document_id:
        prev = _doc(db, ctx.case.id, replaces_document_id)
        group, version = prev.version_group, 1 + max(d.version for d in db.scalars(select(Document).where(Document.version_group == prev.version_group)).all())
    doc_id = uuid.uuid4()
    key = f"{ctx.case.org_id}/{ctx.case.id}/{doc_id}{ext}"  # server-generated key; client filename never touches the path
    get_storage().put(key, data)
    doc = Document(id=doc_id, org_id=ctx.case.org_id, case_id=ctx.case.id, uploader_id=ctx.user.id, filename=name, mime_type=ALLOWED[ext], size_bytes=len(data),
                   sha256=hashlib.sha256(data).hexdigest(), storage_key=key, doc_type=None if doc_type == "auto" else doc_type,
                   doc_type_source="classifier" if doc_type == "auto" else "user", is_synthetic=is_synthetic or ctx.case.is_synthetic,
                   version_group=group, version=version, processing_status="uploaded")
    db.add(doc)
    audit(db, ctx.user, "document.upload", "document", doc_id, {"case_id": str(ctx.case.id), "version": version})
    db.commit()
    bg.add_task(process_document, doc_id)
    return to_dict(doc, exclude={"extracted_text"})


@router.get("")
def list_docs(ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    return [to_dict(d, exclude={"extracted_text"}) for d in db.scalars(select(Document).where(Document.case_id == ctx.case.id).order_by(Document.created_at.desc())).all()]


@router.get("/{document_id}")
def get_doc(document_id: uuid.UUID, ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    d = _doc(db, ctx.case.id, document_id)
    return to_dict(d, exclude={"extracted_text"})


@router.get("/{document_id}/text")
def text(document_id: uuid.UUID, ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    d = _doc(db, ctx.case.id, document_id)
    pages = db.scalars(select(DocumentPage).where(DocumentPage.document_id == d.id).order_by(DocumentPage.page_no)).all()
    return {"id": str(d.id), "processing_status": d.processing_status, "processing_error": d.processing_error, "page_count": d.page_count,
            "pages": [{"page": p.page_no, "text": p.text, "ocr": p.ocr} for p in pages]}


@router.get("/{document_id}/extractions")
def extractions(document_id: uuid.UUID, kind: str | None = None, ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    d = _doc(db, ctx.case.id, document_id)
    stmt = select(Extraction).where(Extraction.document_id == d.id)
    if kind:
        stmt = stmt.where(Extraction.kind == kind)
    return [to_dict(e) for e in db.scalars(stmt.order_by(Extraction.kind, Extraction.page)).all()]


class ReviewIn(BaseModel):
    review_status: str  # confirmed | rejected | edited
    edited_value: str | None = None


@router.patch("/{document_id}/extractions/{extraction_id}")
def review_extraction(document_id: uuid.UUID, extraction_id: uuid.UUID, body: ReviewIn, ctx: CaseCtx = Depends(get_case_write), db: Session = Depends(get_db)):
    d = _doc(db, ctx.case.id, document_id)
    e = db.get(Extraction, extraction_id)
    if not e or e.document_id != d.id:
        raise HTTPException(404, "Extraction not found")
    if body.review_status not in ("confirmed", "rejected", "edited"):
        raise HTTPException(422, "review_status must be confirmed|rejected|edited")
    e.review_status, e.edited_value = body.review_status, body.edited_value
    d.review_status = "reviewed"
    audit(db, ctx.user, "extraction.review", "extraction", e.id, {"status": body.review_status})
    db.commit()
    return to_dict(e)


@router.post("/{document_id}/reprocess", status_code=202)
def reprocess(document_id: uuid.UUID, bg: BackgroundTasks, ctx: CaseCtx = Depends(get_case_write), db: Session = Depends(get_db)):
    d = _doc(db, ctx.case.id, document_id)
    d.processing_status = "uploaded"
    db.commit()
    bg.add_task(process_document, d.id)
    return {"status": "queued"}


@router.get("/{document_id}/download")
def download(document_id: uuid.UUID, ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    d = _doc(db, ctx.case.id, document_id)
    audit(db, ctx.user, "document.download", "document", d.id)
    db.commit()
    return Response(get_storage().get(d.storage_key), media_type=d.mime_type, headers={"Content-Disposition": f'attachment; filename="{d.filename}"'})


@router.get("/{document_id}/versions")
def versions(document_id: uuid.UUID, ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    d = _doc(db, ctx.case.id, document_id)
    rows = db.scalars(select(Document).where(Document.version_group == d.version_group, Document.case_id == ctx.case.id).order_by(Document.version)).all()
    return [{"id": str(r.id), "version": r.version, "filename": r.filename, "sha256": r.sha256, "created_at": r.created_at.isoformat()} for r in rows]


class CompareIn(BaseModel):
    document_a: uuid.UUID
    document_b: uuid.UUID


@router.post("/compare")
def compare(body: CompareIn, ctx: CaseCtx = Depends(get_case_read), db: Session = Depends(get_db)):
    packs = []
    for did in (body.document_a, body.document_b):
        d = _doc(db, ctx.case.id, did)
        if d.processing_status != "extracted":
            raise HTTPException(409, f"{d.filename} is not processed ({d.processing_status})")
        items = [{"kind": e.kind, "label": e.label, "value": e.edited_value or e.value, "page": e.page} for e in
                 db.scalars(select(Extraction).where(Extraction.document_id == d.id, Extraction.review_status != "rejected")).all()]
        packs.append({"name": d.filename, "items": items})
    return docintel.compare(*packs)
