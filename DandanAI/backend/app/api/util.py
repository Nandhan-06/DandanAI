import uuid
from datetime import date, datetime

from sqlalchemy import inspect

HIDDEN = {"password_hash", "token_version", "embedding"}


def to_dict(obj, exclude: set[str] | None = None, include_text: bool = True) -> dict:
    out = {}
    for c in inspect(obj).mapper.column_attrs:
        if c.key in HIDDEN or (exclude and c.key in exclude):
            continue
        v = getattr(obj, c.key)
        if isinstance(v, (uuid.UUID,)):
            v = str(v)
        elif isinstance(v, (datetime, date)):
            v = v.isoformat()
        out[c.key] = v
    return out
