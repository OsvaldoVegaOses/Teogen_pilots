from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d[\d\s\-]{7,}\d)\b")
_RUT_RE = re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b")
_LONG_ID_RE = re.compile(r"\b\d{8,}\b")

_PII_PATTERNS = {
    "email": _EMAIL_RE,
    "rut": _RUT_RE,
    "id": _LONG_ID_RE,
    "phone": _PHONE_RE,
}


def detect_pii_types(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for pii_type, pattern in _PII_PATTERNS.items():
        if pattern.search(text):
            found.append(pii_type)
    return found


def redact_pii_text(text: str) -> str:
    if not text:
        return text
    out = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    out = _RUT_RE.sub("[REDACTED_RUT]", out)
    out = _LONG_ID_RE.sub("[REDACTED_ID]", out)
    out = _PHONE_RE.sub("[REDACTED_PHONE]", out)
    return out
