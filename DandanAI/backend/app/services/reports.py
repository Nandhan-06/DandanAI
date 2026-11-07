"""Report rendering (Markdown source of truth) and exports (PDF via ReportLab, DOCX via python-docx)."""
import io
import re

from app.services.guardrails import DISCLAIMER


def banner(mode: str, status: str, synthetic: bool) -> list[str]:
    out = []
    if status != "approved":
        out.append("> **DRAFT — NOT REVIEWED.** Requires advocate approval before reliance.")
    if mode == "mock":
        out.append("> **MOCK MODE:** generated with deterministic mock providers and no live AI. Not real legal research.")
    if synthetic:
        out.append("> **SYNTHETIC SOURCES:** authorities cited below are fictional test data, not real law.")
    return out


def cite_line(c: dict) -> str:
    bits = [c.get("title"), c.get("pinpoint"), c.get("court"), c.get("citation"), c.get("date")]
    tag = f"[{c.get('authority_class')}; {c.get('verification_status')}]"
    return " — ".join(b for b in bits if b) + " " + tag


def render_markdown(title: str, sections: list[tuple[str, list[str]]], *, mode: str, status: str, synthetic: bool, meta: dict | None = None) -> str:
    md = [f"# {title}", ""] + banner(mode, status, synthetic) + [""]
    if meta:
        md += [f"*{k}:* {v}  " for k, v in meta.items()] + [""]
    for head, lines in sections:
        md += [f"## {head}", ""] + lines + [""]
    md += ["---", f"*{DISCLAIMER}*"]
    return "\n".join(md)


def to_docx(markdown: str) -> bytes:
    import docx
    d = docx.Document()
    for line in markdown.splitlines():
        if line.startswith("# "):
            d.add_heading(line[2:], 0)
        elif line.startswith("## "):
            d.add_heading(line[3:], 1)
        elif line.startswith("### "):
            d.add_heading(line[4:], 2)
        elif line.startswith(("- ", "* ")):
            d.add_paragraph(re.sub(r"[*_`]", "", line[2:]), style="List Bullet")
        elif line.strip() and line.strip() != "---":
            d.add_paragraph(re.sub(r"[*_`>]", "", line).strip())
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def to_pdf(markdown: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from xml.sax.saxutils import escape
    ss = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="DandanAI report")
    flow = []
    for line in markdown.splitlines():
        t = escape(re.sub(r"[*_`>]", "", line)).strip()
        if line.startswith("# "):
            flow.append(Paragraph(escape(line[2:]), ss["Title"]))
        elif line.startswith("## "):
            flow.append(Paragraph(escape(line[3:]), ss["Heading2"]))
        elif t and t != "---":
            flow.append(Paragraph(t, ss["BodyText"]))
        else:
            flow.append(Spacer(1, 6))
    doc.build(flow)
    return buf.getvalue()
