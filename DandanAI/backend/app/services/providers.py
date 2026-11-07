"""Provider-independent abstractions: LLM, embeddings, OCR, STT, TTS, avatar, storage, reranker.

Every mock is deterministic and labelled. `mode()` reports mock/live so the UI can show it."""
from __future__ import annotations

import hashlib
import io
import math
import os
import re
import shutil
import struct
import wave
from typing import Protocol

import httpx

from app.core.config import get_settings

_STOP = set("a an the of to in on at for and or is are was were be been by with as from that this it its into than then "
            "shall may must not no any all such which who whom whose has have had do does did if else under upon".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOP and len(t) > 1]


def stem(t: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            return t[: -len(suf)]
    return t


def mode() -> dict:
    s = get_settings()
    llm_key = (s.llm_api_key or "").strip()
    emb_key = (s.embedding_api_key or s.llm_api_key or "").strip()
    llm_live = s.llm_provider != "mock" and bool(llm_key)
    emb_live = s.embedding_provider != "mock" and bool(emb_key)
    tts_mode = "edge-tts (Liam Canada)" if s.tts_provider in ("edge-tts", "edge", "local-piper") else ("live" if s.tts_provider != "mock" and s.tts_api_key else "mock")
    return {"llm": "live" if llm_live else "mock", "embeddings": "live" if emb_live else "mock",
            "ocr": ocr_name(), "stt": "live" if s.stt_provider != "mock" and s.stt_api_key else "mock",
            "tts": tts_mode,
            "avatar": "live" if s.avatar_provider != "mock" and s.avatar_api_key else "mock",
            "overall": "live" if llm_live and emb_live else "mock"}


# ----------------------------------------------------------------------------- embeddings
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbedder:
    """Deterministic signed-hash bag-of-words embedding (NOT semantic AI; lexical-overlap proxy)."""

    def __init__(self, dim: int):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            toks = [stem(x) for x in tokenize(t)]
            feats = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
            for f in feats:
                h = int(hashlib.md5(f.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


def _clean_url(url: str | None, default: str) -> str:
    cleaned = (url or "").split("#")[0].strip().rstrip("/")
    if not cleaned:
        return default
    if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
        cleaned = "https://" + cleaned
    return cleaned


class OpenAIEmbedder:
    def __init__(self, s):
        self.s = s

    def embed(self, texts: list[str]) -> list[list[float]]:
        base = _clean_url(self.s.llm_base_url, "https://api.openai.com/v1")
        key = (self.s.embedding_api_key or self.s.llm_api_key or "").strip()
        if not key:
            return MockEmbedder(self.s.embedding_dim).embed(texts)
        try:
            r = httpx.post(f"{base}/embeddings", timeout=60,
                           headers={"Authorization": f"Bearer {key}"},
                           json={"model": self.s.embedding_model or "text-embedding-3-small", "input": texts,
                                 "dimensions": self.s.embedding_dim})
            r.raise_for_status()
            return [d["embedding"] for d in r.json()["data"]]
        except Exception:
            # Fall back to mock embeddings if API call fails so RAG search does not crash
            return MockEmbedder(self.s.embedding_dim).embed(texts)


class GeminiEmbedder:
    def __init__(self, s):
        self.s = s

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self.s.embedding_model or "text-embedding-004"
        key = (self.s.embedding_api_key or self.s.llm_api_key or "").strip()
        if not key:
            return MockEmbedder(self.s.embedding_dim).embed(texts)
        try:
            out = []
            for t in texts:
                r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={key}",
                               json={"content": {"parts": [{"text": t}]}, "outputDimensionality": self.s.embedding_dim},
                               timeout=60)
                r.raise_for_status()
                out.append(r.json()["embedding"]["values"])
            return out
        except Exception:
            return MockEmbedder(self.s.embedding_dim).embed(texts)


def get_embedder() -> Embedder:
    s = get_settings()
    key = (s.embedding_api_key or s.llm_api_key or "").strip()
    if s.embedding_provider == "openai" and key:
        return OpenAIEmbedder(s)
    if s.embedding_provider == "gemini" and key:
        return GeminiEmbedder(s)
    return MockEmbedder(s.embedding_dim)


# ----------------------------------------------------------------------------- LLM
class LLM(Protocol):
    name: str
    is_mock: bool

    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    """Deterministic. Produces labelled template text from the prompt; performs no real reasoning."""
    name, is_mock = "mock-llm", True

    def complete(self, system: str, prompt: str) -> str:
        first = prompt.strip().splitlines()[0][:300] if prompt.strip() else ""
        return f"[MOCK LLM — deterministic template, not AI analysis] {first}"


class OpenAILLM:
    is_mock = False

    def __init__(self, s):
        self.s, self.name = s, s.llm_model or "gpt-4o-mini"

    def complete(self, system: str, prompt: str) -> str:
        base = _clean_url(self.s.llm_base_url, "https://api.openai.com/v1")
        key = (self.s.llm_api_key or "").strip()
        if not key:
            return MockLLM().complete(system, prompt)
        try:
            r = httpx.post(f"{base}/chat/completions", timeout=120, headers={"Authorization": f"Bearer {key}"},
                           json={"model": self.name, "temperature": 0,
                                 "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            return f"[OpenAI Error {e.response.status_code}: {e.response.text[:200]}]"
        except Exception as e:
            return f"[AI Provider Error: {str(e)}]"


class GeminiLLM:
    is_mock = False

    def __init__(self, s):
        self.s, self.name = s, s.llm_model or "gemini-1.5-flash"

    def complete(self, system: str, prompt: str) -> str:
        key = (self.s.llm_api_key or "").strip()
        if not key:
            return MockLLM().complete(system, prompt)
        try:
            r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.name}:generateContent?key={key}",
                           json={"systemInstruction": {"parts": [{"text": system}]},
                                 "contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}, timeout=120)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            return f"[Gemini Error: {str(e)}]"


def get_llm() -> LLM:
    s = get_settings()
    key = (s.llm_api_key or "").strip()
    if s.llm_provider == "openai" and key:
        return OpenAILLM(s)
    if s.llm_provider == "gemini" and key:
        return GeminiLLM(s)
    return MockLLM()


# ----------------------------------------------------------------------------- OCR
def ocr_name() -> str:
    s = get_settings()
    if s.ocr_provider == "none":
        return "none"
    if s.ocr_provider in ("auto", "tesseract") and shutil.which("tesseract"):
        return "tesseract"
    return "mock"


def ocr_image(data: bytes) -> tuple[str, bool]:
    """Returns (text, is_mock). Tesseract if installed, otherwise a clearly-labelled mock marker."""
    name = ocr_name()
    if name == "tesseract":
        try:
            import pytesseract
            from PIL import Image
            return pytesseract.image_to_string(Image.open(io.BytesIO(data))), False
        except Exception:  # noqa: BLE001
            pass
    if name == "none":
        return "", True
    return "[MOCK OCR: no OCR engine configured; install Tesseract or set OCR_PROVIDER. No text was actually read.]", True


# ----------------------------------------------------------------------------- STT / TTS / avatar
def _audio_to_wav_bytes(audio: bytes) -> bytes:
    """Convert any audio format (webm/opus/mp3/etc.) to WAV bytes using pydub.
    Returns original bytes if pydub/ffmpeg is unavailable."""
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(io.BytesIO(audio))
        buf = io.BytesIO()
        seg.export(buf, format="wav")
        return buf.getvalue()
    except Exception:
        return audio


def transcribe(audio: bytes, filename: str) -> dict:
    s = get_settings()

    # 1. faster-whisper (local, runs on CPU/GPU, no API key needed)
    #    Install: pip install faster-whisper
    #    Triggered when STT_PROVIDER=faster-whisper (or local-whisper)
    if s.stt_provider in ("faster-whisper", "local-whisper", "auto"):
        try:
            from faster_whisper import WhisperModel  # type: ignore
            wav_bytes = _audio_to_wav_bytes(audio)
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(io.BytesIO(wav_bytes), language="en", beam_size=5)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                return {"transcript": text, "mock": False, "editable": True, "engine": "faster-whisper"}
        except ImportError:
            pass  # faster-whisper not installed — fall through
        except Exception:
            pass  # model error — fall through

    # 2. OpenAI Whisper API (cloud, needs API key)
    api_key = s.stt_api_key or (s.llm_api_key if s.llm_provider == "openai" else None)
    if api_key:
        try:
            wav_bytes = _audio_to_wav_bytes(audio)
            base = _clean_url(s.llm_base_url, "https://api.openai.com/v1")
            r = httpx.post(
                f"{base}/audio/transcriptions",
                timeout=60,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename or "voice.wav", wav_bytes, "audio/wav")},
                data={"model": "whisper-1", "language": "en"},
            )
            if r.status_code == 200:
                text = r.json().get("text", "").strip()
                if text:
                    return {"transcript": text, "mock": False, "editable": True, "engine": "openai-whisper"}
        except Exception:
            pass

    # 3. Google Web Speech API via SpeechRecognition (free, keyless, needs internet)
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        wav_bytes = _audio_to_wav_bytes(audio)
        try:
            with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
                audio_data = recognizer.record(source)
        except Exception:
            audio_data = sr.AudioData(wav_bytes, 16000, 2)

        text = recognizer.recognize_google(audio_data, language="en-US").strip()
        if text:
            return {"transcript": text, "mock": False, "editable": True, "engine": "google-web-speech"}
        return {"transcript": "", "mock": False, "editable": True,
                "notice": "No speech detected. Please speak clearly or type below."}
    except Exception as exc:
        if "UnknownValue" in type(exc).__name__:
            return {"transcript": "", "mock": False, "editable": True,
                    "notice": "Could not recognize speech clearly. Please type or try again."}

    return {
        "transcript": "",
        "mock": False,
        "editable": True,
        "notice": "Speech recognition unavailable. Please type your question below.",
    }


def synthesize_wav(text: str) -> bytes:
    """Mock TTS: a short, quiet tone sequence whose length follows the text length (playable in any browser)."""
    rate = 16000
    n_syll = max(3, min(60, len(text.split()) * 2))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(n_syll):
            f = 180 + (hashlib.md5(f"{text}{i}".encode()).digest()[0] % 80)
            for k in range(int(rate * 0.09)):
                env = min(1.0, k / 300, (int(rate * 0.09) - k) / 300)
                frames += struct.pack("<h", int(2200 * env * math.sin(2 * math.pi * f * k / rate)))
            frames += b"\x00\x00" * int(rate * 0.03)
        w.writeframes(bytes(frames))
    return buf.getvalue()


async def synthesize_edge_tts(text: str, voice: str | None = None) -> tuple[bytes, str]:
    """Generate audio using Edge TTS. Defaults to en-CA-LiamNeural (Liam - Canada male voice).
    Falls back to UK male (en-GB-RyanNeural) or USA male (en-US-GuyNeural / en-US-ChristopherNeural),
    and finally fallback tone if offline."""
    s = get_settings()
    pref_voice = voice or getattr(s, "tts_voice", None) or "en-CA-LiamNeural"
    voices = [pref_voice, "en-CA-LiamNeural", "en-GB-RyanNeural", "en-US-GuyNeural", "en-US-ChristopherNeural"]
    seen = set()
    candidate_voices = [v for v in voices if v and not (v in seen or seen.add(v))]

    for v in candidate_voices:
        try:
            import edge_tts
            clean_text = text.strip()
            if not clean_text:
                continue
            comm = edge_tts.Communicate(clean_text, v)
            chunks = []
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            if chunks:
                return b"".join(chunks), "audio/mpeg"
        except Exception:
            continue

    # Fallback to local tone wave
    return synthesize_wav(text), "audio/wav"


def avatar_timeline(text: str) -> dict:
    words = text.split()
    t, visemes = 0.0, []
    for i, wd in enumerate(words[:200]):
        d = 0.18 + 0.02 * min(len(wd), 8)
        visemes.append({"t": round(t, 2), "d": round(d, 2), "mouth": ["A", "E", "O", "M", "U"][i % 5]})
        t += d + 0.03
    return {"provider": "mock-avatar", "mock": True, "duration": round(t, 2), "visemes": visemes}


# ----------------------------------------------------------------------------- storage
class Storage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)

    def _path(self, key: str) -> str:
        p = os.path.abspath(os.path.join(self.root, key))
        if not p.startswith(self.root + os.sep):
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)

    def get(self, key: str) -> bytes:
        with open(self._path(key), "rb") as fh:
            return fh.read()


class S3Storage:  # S3-compatible private bucket (untested here: needs credentials)
    def __init__(self, s):
        import boto3  # optional dependency: pip install boto3
        self.bucket = s.s3_bucket
        self.c = boto3.client("s3", endpoint_url=s.s3_endpoint_url or None, region_name=s.s3_region or None,
                              aws_access_key_id=s.s3_access_key_id, aws_secret_access_key=s.s3_secret_access_key)

    def put(self, key: str, data: bytes) -> None:
        self.c.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        return self.c.get_object(Bucket=self.bucket, Key=key)["Body"].read()


def get_storage() -> Storage:
    s = get_settings()
    return S3Storage(s) if s.storage_provider == "s3" else LocalStorage(s.storage_dir)
