import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.util import to_dict
from app.core.config import get_settings
from app.database import get_db
from app.deps import case_access, get_current_user
from app.models import Conversation, Message, User
from app.services import guardrails, providers
from app.services.audit import audit
from app.services.rag import search_case_docs, search_legal

router = APIRouter(prefix="/api/v1", tags=["chat"])

# Patterns that should never appear in user-facing output
_BRACKET_LABEL = re.compile(
    r"\[(?:SYNTHETIC TEST DATA|MOCK LLM[^\]]*|outcome prediction removed[^\]]*|removed-instruction-like-text)\]",
    re.I,
)


def _clean_response(text: str) -> str:
    """Remove internal labels (SYNTHETIC TEST DATA, MOCK LLM …) from displayed text."""
    # Remove standalone bracketed labels (possibly with comma prefix)
    text = _BRACKET_LABEL.sub("", text)
    # Clean up doubled commas/spaces left after removal e.g. "[primary, ]" → "[primary]"
    text = re.sub(r",\s*\]", "]", text)
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _build_summary(llm_analysis: str, hits: list[dict], question: str) -> str:
    """Build a concise bullet-point summary from the LLM analysis and citation titles."""
    lines = ["**Summary**"]

    # Extract key sentences from the LLM analysis (first 3 sentences or 400 chars)
    analysis_clean = _BRACKET_LABEL.sub("", llm_analysis).strip()
    if analysis_clean and not analysis_clean.startswith("["):
        sentences = re.split(r"(?<=[.!?])\s+", analysis_clean)
        summary_body = " ".join(sentences[:3]).strip()
        if summary_body:
            lines.append(summary_body)

    # List the sources consulted (without synthetic labels)
    if hits:
        source_names = []
        for h in hits[:3]:
            title = h["citation"].get("title", "")
            section = h["citation"].get("pinpoint", "")
            if title:
                source_names.append(f"{title}" + (f" ({section})" if section else ""))
        if source_names:
            lines.append("\nRelevant sources consulted:")
            for s in source_names:
                lines.append(f"• {s}")

    return "\n".join(lines)


def _voice_summary(llm_analysis: str, hits: list[dict]) -> str:
    """Plain-text version of the summary for TTS (no markdown)."""
    analysis_clean = _BRACKET_LABEL.sub("", llm_analysis).strip()
    sentences = re.split(r"(?<=[.!?])\s+", analysis_clean)
    body = " ".join(s for s in sentences[:3] if s).strip()

    if hits:
        titles = [h["citation"].get("title", "") for h in hits[:2] if h["citation"].get("title")]
        if titles:
            body += " Based on: " + "; ".join(titles) + "."

    return body or "No relevant sources were found in the knowledge base for this question."


class ConvIn(BaseModel):
    title: str | None = None
    case_id: uuid.UUID | None = None


class ConvPatch(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MsgIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    modality: str = "text"  # text | voice (voice = edited transcript)


def _conv(db: Session, user: User, cid: uuid.UUID) -> Conversation:
    c = db.get(Conversation, cid)
    if not c or c.user_id != user.id:  # conversations are private to their creator
        raise HTTPException(404, "Conversation not found")
    return c


@router.post("/chat/conversations", status_code=201)
def new_conv(body: ConvIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.case_id:
        case_access(db, user, body.case_id)
    c = Conversation(org_id=user.org_id, user_id=user.id, case_id=body.case_id, title=(body.title or "New conversation")[:200])
    db.add(c)
    db.commit()
    return to_dict(c)


@router.get("/chat/conversations")
def convs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [to_dict(c) for c in db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.created_at.desc())).all()]


@router.get("/chat/conversations/{cid}/messages")
def msgs(cid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _conv(db, user, cid)
    return [to_dict(m) for m in db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at)).all()]


@router.patch("/chat/conversations/{cid}")
def rename_conv(cid: uuid.UUID, body: ConvPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _conv(db, user, cid)
    c.title = body.title.strip()[:200]
    db.commit()
    return to_dict(c)


@router.delete("/chat/conversations/{cid}", status_code=204)
def delete_conv(cid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _conv(db, user, cid)
    db.execute(Message.__table__.delete().where(Message.conversation_id == c.id))
    db.delete(c)
    db.commit()


@router.post("/chat/conversations/{cid}/messages", status_code=201)
def send(cid: uuid.UUID, body: MsgIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _conv(db, user, cid)
    if body.modality not in ("text", "voice"):
        raise HTTPException(422, "modality must be text|voice")
    q, flags = guardrails.clean_input(body.content, max_chars=4000)
    db.add(Message(conversation_id=c.id, role="user", content=q, modality=body.modality, meta={"input_flags": flags}))
    legal = search_legal(db, q, top_k=3)
    case_hits = []
    if c.case_id:
        case_access(db, user, c.case_id)  # re-check access on every turn
        case_hits = search_case_docs(db, q, [c.case_id], user.org_id, top_k=2)
    llm = providers.get_llm()

    if legal["hits"] or case_hits:
        # Build source lines — strip [SYNTHETIC TEST DATA] label from display
        source_lines = []
        for h in legal["hits"]:
            cit = h["citation"]
            is_synth = cit.get("is_synthetic", False)
            label = f"[{cit['authority_class']}{'  — test data' if is_synth else ''}]"
            source_lines.append(
                f"- {cit['title']} ({cit['pinpoint']}) {label}: {cit['excerpt'][:240]}"
            )
        for h in case_hits:
            source_lines.append(f"- Case document p.{h['page']}: {h['text'][:200]}")

        llm_analysis = llm.complete("Be neutral and cite only given sources.", q)
        llm_clean = _clean_response(llm_analysis)

        # Summary block
        summary_md = _build_summary(llm_analysis, legal["hits"], q)
        voice_summary = _voice_summary(llm_analysis, legal["hits"])

        # Full displayed response
        sources_block = "**Sources consulted:**\n" + "\n".join(source_lines)
        text = f"{sources_block}\n\n{llm_clean}\n\n{summary_md}"
    else:
        text = "I could not find sufficient supporting information in the knowledge base to answer this question. No legal conclusion is offered."
        summary_md = "**Summary**\nNo relevant sources were found in the knowledge base for this question."
        voice_summary = "No relevant sources were found in the knowledge base for this question."
        llm_analysis = ""

    text, oflags = guardrails.check_output(text)
    text = _clean_response(text)
    text += f"\n\n*{guardrails.DISCLAIMER}*"

    m = Message(
        conversation_id=c.id,
        role="assistant",
        content=text,
        modality="text",
        citations=[h["citation"] for h in legal["hits"]],
        meta={
            "mode": providers.mode()["overall"],
            "confidence": legal["confidence"],
            "coverage_gaps": legal["coverage_gaps"],
            "output_flags": oflags,
            "case_document_hits": case_hits,
            "summary": summary_md,
            "voice_summary": voice_summary,          # plain text for TTS
            "voice_full": _clean_response(text),     # full response cleaned for TTS
        },
    )
    db.add(m)
    if c.title == "New conversation":
        c.title = q[:60]
    audit(db, user, "chat.message", "conversation", c.id)
    db.commit()
    return to_dict(m)


# ------------------------------------------------------------------ voice adapters (mock by default)
@router.post("/voice/transcribe")
async def transcribe(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    data = await file.read(10 * 1024 * 1024 + 1)
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(422, "Audio must be 1 byte – 10 MB")
    return {**providers.transcribe(data, file.filename or "audio"), "mode": providers.mode()["stt"]}


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/voice/tts")
async def tts(body: TTSIn, user: User = Depends(get_current_user)):
    s = get_settings()
    if s.tts_provider in ("edge-tts", "edge", "auto", "local-piper") or s.tts_provider != "mock":
        audio_data, media_type = await providers.synthesize_edge_tts(body.text)
        return Response(audio_data, media_type=media_type, headers={"X-Voice-Mode": "edge-tts:en-CA-LiamNeural"})
    return Response(providers.synthesize_wav(body.text), media_type="audio/wav", headers={"X-Voice-Mode": providers.mode()["tts"]})


@router.post("/voice/avatar")
def avatar(body: TTSIn, user: User = Depends(get_current_user)):
    return {**providers.avatar_timeline(body.text), "mode": providers.mode()["avatar"]}
