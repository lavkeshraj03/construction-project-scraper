"""app/processors/cleaner.py — Field-level cleaning functions."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _strip(value: Optional[str]) -> str:
    if not value:
        return ""
    # Normalise unicode, collapse whitespace
    value = unicodedata.normalize("NFKC", str(value))
    return " ".join(value.split()).strip()


_CURRENCY_RE = re.compile(r"[₹\$€£]")
_NON_DIGIT   = re.compile(r"[^\d.]")
_PHONE_CLEAN = re.compile(r"[^\d\+]")


# ─── Public cleaners ──────────────────────────────────────────────────────────

def clean_name(value: Optional[str]) -> str:
    """Normalise company / person names to title case, strip legal suffixes noise."""
    v = _strip(value)
    if not v:
        return "Not Found"
    # Remove trailing dots from abbreviations before re-normalising
    # (prevents double periods like 'Pvt.. Ltd..')
    v = re.sub(r"\bPVT\.?\s*LTD\.?", "Pvt. Ltd.", v, flags=re.IGNORECASE)
    v = re.sub(r"(?<!Pvt)\bLTD\.?", "Ltd.", v, flags=re.IGNORECASE)
    v = re.sub(r"(?<!Pvt\.)\bPVT\.?", "Pvt.", v, flags=re.IGNORECASE)
    v = re.sub(r"\bLLP\b", "LLP", v, flags=re.IGNORECASE)
    v = re.sub(r"\bINFRA\b", "Infra", v, flags=re.IGNORECASE)
    # Collapse any accidental double periods
    v = re.sub(r"\.{2,}", ".", v)
    # Title-case remaining words
    words = v.split()
    titled = []
    small = {"and", "of", "the", "a", "an", "for", "at", "in", "on", "by", "to"}
    for i, w in enumerate(words):
        if i == 0 or w.lower() not in small:
            titled.append(w.capitalize())
        else:
            titled.append(w.lower())
    return " ".join(titled)


def clean_location(value: Optional[str]) -> str:
    v = _strip(value)
    return v if v else "Not Found"


def clean_district(value: Optional[str]) -> str:
    v = _strip(value).title()
    return v if v else "Unknown"


def clean_pincode(value: Optional[str]) -> str:
    if not value:
        return "Not Found"
    digits = re.sub(r"\D", "", str(value))
    return digits if len(digits) == 6 else "Not Found"


def clean_phone(value: Optional[str]) -> str:
    if not value:
        return "Not Found"
    cleaned = _PHONE_CLEAN.sub("", str(value)).strip()
    if len(cleaned) < 7:
        return "Not Found"
    # Normalise Indian numbers
    if cleaned.startswith("0"):
        cleaned = "+91" + cleaned[1:]
    if len(cleaned) == 10 and not cleaned.startswith("+"):
        cleaned = "+91" + cleaned
    return cleaned


def clean_email(value: Optional[str]) -> str:
    if not value:
        return "Not Found"
    return _strip(value).lower()


def clean_currency(value: Optional[str]) -> str:
    """Return a normalised string like '₹ 50,00,00,000' or the original cleaned value."""
    if not value:
        return "Not Found"
    v = _CURRENCY_RE.sub("", str(value)).strip()
    # Try to parse a number
    try:
        num = float(_NON_DIGIT.sub("", v))
        if num >= 1:
            return f"₹ {num:,.0f}"
    except (ValueError, TypeError):
        pass
    return _strip(value) or "Not Found"


def clean_date(value: Optional[str]) -> str:
    v = _strip(value)
    return v if v else "Not Found"


def clean_completion_percentage(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def clean_stage(value: Optional[str]) -> str:
    """Map raw status text to canonical construction stage."""
    if not value:
        return "Unknown"
    v = value.strip().lower()

    stage_map = {
        "planning":            "Planning",
        "plan":                "Planning",
        "approved":            "Approved",
        "sanctioned":          "Approved",
        "pre-construction":    "Pre-Construction",
        "pre construction":    "Pre-Construction",
        "under construction":  "Under Construction",
        "construction":        "Under Construction",
        "ongoing":             "Under Construction",
        "active":              "Under Construction",
        "in progress":         "Under Construction",
        "advanced":            "Advanced Construction",
        "near completion":     "Near Completion",
        "nearing completion":  "Near Completion",
        "nearly complete":     "Near Completion",
        "completed":           "Completed",
        "complete":            "Completed",
        "finished":            "Completed",
        "possession":          "Completed",
        "handed over":         "Completed",
        "lapsed":              "Completed",
    }
    for key, canonical in stage_map.items():
        if key in v:
            return canonical
    return "Unknown"


def clean_text_field(value: Optional[str], fallback: str = "Not Found") -> str:
    v = _strip(value)
    return v if v else fallback
