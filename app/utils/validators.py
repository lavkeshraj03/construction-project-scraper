"""app/utils/validators.py — Basic field validators."""

from __future__ import annotations

import re
from typing import Optional


_PHONE_RE = re.compile(r"[\+\d][\d\s\-\(\)]{7,15}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_RERA_RE  = re.compile(r"P\d{2}\d+\d{4}[A-Z]+\d+", re.IGNORECASE)


def is_valid_phone(value: str) -> bool:
    return bool(_PHONE_RE.fullmatch(value.strip()))


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.fullmatch(value.strip()))


def extract_emails(text: str) -> list[str]:
    return _EMAIL_RE.findall(text)


def extract_phones(text: str) -> list[str]:
    return _PHONE_RE.findall(text)


def extract_rera_numbers(text: str) -> list[str]:
    return _RERA_RE.findall(text)


def is_placeholder(value: Optional[str]) -> bool:
    """Return True if value is a known placeholder (Not Found / Unknown / None)."""
    if value is None:
        return True
    return value.strip().lower() in ("not found", "unknown", "n/a", "na", "none", "")
