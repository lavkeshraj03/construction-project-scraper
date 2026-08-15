"""app/processors/scorer.py — Rule-based lead scoring (transparent, configurable).

Maximum score: 100
Classification:
    80–100 → Very High
    60–79  → High
    40–59  → Medium
    0–39   → Low
"""

from __future__ import annotations

from typing import Any

# ─── Scoring rules ─────────────────────────────────────────────────────────────
# Each rule is a (points, condition_fn) pair.
# Modify RULES to adjust scoring without touching logic.

def _has_field(rec: dict, key: str) -> bool:
    v = str(rec.get(key) or "").strip()
    return v not in ("", "Not Found", "Unknown", "None", "not found", "unknown")


RULES: list[tuple[int, Any]] = [
    (25, lambda r: r.get("current_stage") in (
        "Under Construction", "Advanced Construction", "Near Completion")),
    (25, lambda r: _large_project(r)),
    (20, lambda r: r.get("material_required") == "Yes"),
    (10, lambda r: _has_field(r, "decision_maker")),
    (5,  lambda r: _has_field(r, "mobile")),
    (5,  lambda r: _has_field(r, "email")),
    (5,  lambda r: _has_field(r, "architect")),
    (5,  lambda r: _has_field(r, "contractor")),
]

MAX_SCORE = sum(pts for pts, _ in RULES)  # = 100


def _large_project(rec: dict) -> bool:
    """Consider 'large' if project value appears to be ≥ 1 crore."""
    pv = str(rec.get("project_value") or "")
    try:
        # Remove currency symbols and commas, parse
        digits = "".join(c for c in pv if c.isdigit() or c == ".")
        if not digits:
            return False
        num = float(digits)
        # Values are stored as raw numbers; 1 crore = 10,000,000
        return num >= 10_000_000
    except (ValueError, TypeError):
        return False


def calculate_lead_score(record: dict[str, Any]) -> dict[str, Any]:
    """Compute and set lead_score on the record (mutates in-place)."""
    score = 0
    for pts, condition in RULES:
        try:
            if condition(record):
                score += pts
        except Exception:
            pass
    record["lead_score"] = min(score, MAX_SCORE)
    return record


def lead_priority(score: int) -> str:
    if score >= 80:
        return "Very High"
    if score >= 60:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"
