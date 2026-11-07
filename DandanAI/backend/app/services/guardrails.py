"""Input/output guardrails and the mandatory legal disclaimer."""
import re

DISCLAIMER = ("DandanAI is a decision-support tool for legal professionals. It does not provide legal advice and does "
              "not replace the judgment of a qualified advocate or a court. All outputs require independent human "
              "verification against authoritative sources before any reliance.")

MAX_INPUT_CHARS = 20000
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INJECTION = re.compile(r"(ignore (all |any )?(previous|prior|above) (instructions|prompts)|disregard (the )?system prompt|"
                        r"you are now|reveal (your )?(system )?prompt|act as (an? )?(unrestricted|jailbroken))", re.I)
# Outcome / probability predictions are never produced.
_PREDICTION = re.compile(r"(\b(will|would|is likely to|is certain to)\s+(be\s+)?(convicted|acquitted|found guilty|win|lose)\b|"
                         r"\b(the )?(accused|defendant|respondent) is guilty\b|\bguilty beyond\b|"
                         r"\b\d{1,3}(\.\d+)?\s?%\s*(chance|probability|likelihood|success)|"
                         r"\b(chance|probability|likelihood) of (success|conviction|acquittal)\s*(is|:)?\s*\d)", re.I)


def clean_input(text: str, *, max_chars: int = MAX_INPUT_CHARS) -> tuple[str, list[str]]:
    flags: list[str] = []
    text = _CTRL.sub(" ", text or "").strip()
    if len(text) > max_chars:
        text = text[:max_chars]
        flags.append("input_truncated")
    if _INJECTION.search(text):
        flags.append("prompt_injection_suspected")
        text = _INJECTION.sub("[removed-instruction-like-text]", text)
    return text, flags


def check_output(text: str) -> tuple[str, list[str]]:
    """Redact outcome predictions. Returns (safe_text, flags)."""
    flags: list[str] = []
    if _PREDICTION.search(text or ""):
        flags.append("outcome_prediction_redacted")
        text = _PREDICTION.sub("[outcome prediction removed — DandanAI does not predict guilt, conviction or success]", text)
    return text, flags


def scan_structure(obj) -> list[str]:
    """Recursively scan structured output for prediction language."""
    flags: list[str] = []
    if isinstance(obj, str):
        _, f = check_output(obj)
        flags += f
    elif isinstance(obj, dict):
        for v in obj.values():
            flags += scan_structure(v)
    elif isinstance(obj, list):
        for v in obj:
            flags += scan_structure(v)
    return sorted(set(flags))
