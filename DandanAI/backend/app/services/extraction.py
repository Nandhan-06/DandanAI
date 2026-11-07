"""Text extraction with page-level provenance: PDF (PyMuPDF), DOCX (python-docx), images (OCR adapter)."""
import io
from dataclasses import dataclass, field

from app.services.providers import ocr_image

ALLOWED = {".pdf": "application/pdf",
           ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
           ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MIN_TEXT_CHARS = 20


@dataclass
class Page:
    no: int
    text: str
    ocr: bool = False


@dataclass
class Extracted:
    status: str = "extracted"
    pages: list[Page] = field(default_factory=list)
    error: str | None = None
    mock_ocr: bool = False

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)


def sniff_ok(ext: str, data: bytes) -> bool:
    if ext == ".pdf":
        return data[:5] == b"%PDF-"
    if ext == ".docx":
        return data[:2] == b"PK"
    if ext == ".png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if ext in (".jpg", ".jpeg"):
        return data[:3] == b"\xff\xd8\xff"
    return False


def extract(ext: str, data: bytes) -> Extracted:
    try:
        if ext == ".pdf":
            return _pdf(data)
        if ext == ".docx":
            return _docx(data)
        return _image(data)
    except Exception as e:  # noqa: BLE001
        return Extracted(status="failed", error=f"{type(e).__name__}: {e}"[:500])


def _pdf(data: bytes) -> Extracted:
    import pymupdf
    doc = pymupdf.open(stream=data, filetype="pdf")
    ex = Extracted()
    for i, page in enumerate(doc, start=1):
        txt = page.get_text("text").strip()
        if len(txt) < MIN_TEXT_CHARS:  # no text layer -> OCR adapter on the rendered page
            png = page.get_pixmap(dpi=200).tobytes("png")
            otxt, is_mock = ocr_image(png)
            if otxt and not is_mock:
                ex.pages.append(Page(i, otxt.strip(), ocr=True))
                continue
            if is_mock and otxt:
                ex.mock_ocr = True
            ex.pages.append(Page(i, "", ocr=True))
            continue
        ex.pages.append(Page(i, txt))
    if not any(p.text for p in ex.pages):
        ex.status = "extracted_mock_ocr" if ex.mock_ocr else "needs_ocr"
        if ex.mock_ocr:
            ex.error = "No OCR engine available: scanned pages were NOT read. Install Tesseract and re-process."
        else:
            ex.error = "No text layer and OCR disabled"
    return ex


def _docx(data: bytes) -> Extracted:
    import docx
    d = docx.Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    # DOCX has no fixed pagination: the whole document is provenance "page 1" (paragraph order preserved)
    ex = Extracted(pages=[Page(1, "\n".join(parts))])
    if not ex.text.strip():
        ex.status, ex.error = "failed", "Empty document"
    return ex


def _image(data: bytes) -> Extracted:
    otxt, is_mock = ocr_image(data)
    if is_mock:
        # The mock marker is recorded for transparency but is NOT treated as document content.
        return Extracted(status="extracted_mock_ocr" if otxt else "needs_ocr", pages=[Page(1, "", ocr=True)],
                         error="No OCR engine available: image text was NOT read. Install Tesseract and re-process.",
                         mock_ocr=True)
    return Extracted(pages=[Page(1, otxt.strip(), ocr=True)])
