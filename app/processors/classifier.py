"""app/processors/classifier.py — Material category and project type classification."""

from __future__ import annotations

import re
from typing import Any

_MATERIAL_PATTERNS: dict[str, list[str]] = {
    "Granite": [
        "granite", "granit", "g-1", "g1 granite", "black galaxy", "tan brown",
        "absolute black", "steel grey", "kashmir white",
    ],
    "Marble": [
        "marble", "makrana", "statuario", "carrara", "onyx", "travertine",
        "white marble", "italian marble",
    ],
    "Quartz": [
        "quartz", "engineered stone", "silestone", "caesarstone", "compac",
    ],
    "Kota": [
        "kota", "kota stone", "kota blue", "kota brown",
    ],
}

_CONSTRUCTION_TERMS = re.compile(
    r"\b(construction|building|civil|infrastructure|development|renovation|"
    r"residential|commercial|hospital|school|office|project|complex|tower|"
    r"housing|society|apartments|township|mall|plaza|hotel|resort)\b",
    re.IGNORECASE,
)


def classify_materials(record: dict[str, Any]) -> dict[str, Any]:
    """
    Inspect raw_data + project_name + source text for material mentions.
    Sets material_required and material_categories on the record (mutates in-place).
    """
    # Combine all text fields for search
    corpus = " ".join(
        str(record.get(f, "") or "")
        for f in (
            "raw_data", "project_name", "project_type",
            "location", "material_required", "material_categories",
        )
    ).lower()

    found: list[str] = []
    for category, keywords in _MATERIAL_PATTERNS.items():
        for kw in keywords:
            if kw in corpus:
                if category not in found:
                    found.append(category)
                break

    if found:
        record["material_required"]   = "Yes"
        record["material_categories"] = ", ".join(found)
    elif record.get("material_required") not in ("Yes", "No"):
        record["material_required"]   = "Unknown"
        record["material_categories"] = record.get("material_categories", "")

    return record


def classify_project_type(record: dict[str, Any]) -> dict[str, Any]:
    """Infer project_type from available text if not already set."""
    if record.get("project_type") and record["project_type"] not in ("Unknown", "Not Found", ""):
        return record

    corpus = " ".join(
        str(record.get(f, "") or "")
        for f in ("project_name", "raw_data")
    ).lower()

    if any(t in corpus for t in ("residential", "housing", "apartment", "flat", "villa")):
        record["project_type"] = "Residential"
    elif any(t in corpus for t in ("commercial", "office", "mall", "plaza", "retail")):
        record["project_type"] = "Commercial"
    elif any(t in corpus for t in ("hospital", "medical", "clinic", "health")):
        record["project_type"] = "Healthcare"
    elif any(t in corpus for t in ("school", "college", "university", "education", "institute")):
        record["project_type"] = "Educational"
    elif any(t in corpus for t in ("hotel", "resort", "hospitality")):
        record["project_type"] = "Hospitality"
    elif any(t in corpus for t in ("road", "bridge", "highway", "flyover", "infrastructure")):
        record["project_type"] = "Infrastructure"
    elif _CONSTRUCTION_TERMS.search(corpus):
        record["project_type"] = "General Construction"
    else:
        record["project_type"] = "Unknown"

    return record
