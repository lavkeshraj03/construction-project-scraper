"""app/processors/deduplicator.py — Detect and mark duplicate project records.

Priority:
1. Strong ID match: RERA number or tender number
2. Fuzzy match: project_name + builder_name + location (using RapidFuzz)

Duplicates are NEVER deleted. They are marked with:
    duplicate_status = "duplicate"
    duplicate_of     = <master_project_id>
"""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from app.utils.logger import get_logger

log = get_logger("deduplicator")

# Minimum combined fuzzy score to consider a duplicate (0–100)
FUZZY_THRESHOLD = 85


def _strong_id_match(candidate: dict, existing: dict) -> bool:
    """Return True if both records share a non-empty RERA or tender number."""
    for field in ("rera_number", "tender_number"):
        cv = (candidate.get(field) or "").strip().upper()
        ev = (existing.get(field) or "").strip().upper()
        if cv and ev and cv == ev:
            return True
    return False


def _fuzzy_match(candidate: dict, existing: dict) -> bool:
    """Return True when project_name + builder + location are very similar."""
    pn_score = fuzz.token_sort_ratio(
        candidate.get("project_name", ""), existing.get("project_name", "")
    )
    bl_score = fuzz.token_sort_ratio(
        candidate.get("builder_name", ""), existing.get("builder_name", "")
    )
    loc_score = fuzz.token_sort_ratio(
        candidate.get("location", ""), existing.get("location", "")
    )
    combined = (pn_score * 0.5) + (bl_score * 0.3) + (loc_score * 0.2)
    return combined >= FUZZY_THRESHOLD


def deduplicate(
    new_records: list[dict[str, Any]],
    existing_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Compare new_records against existing_records (already in DB).
    Also de-dup within new_records themselves.

    Returns new_records with duplicate_status / duplicate_of fields set.
    Never removes records.
    """
    # Build a lookup of existing by project_id
    master_pool: list[dict] = list(existing_records)
    processed: list[dict] = []

    for rec in new_records:
        matched_id: str | None = None

        # Check against already-saved records
        for master in master_pool:
            if master.get("duplicate_status") == "duplicate":
                continue  # don't match against another duplicate
            if _strong_id_match(rec, master):
                matched_id = master["project_id"]
                break
            if _fuzzy_match(rec, master):
                matched_id = master["project_id"]
                break

        if matched_id:
            rec["duplicate_status"] = "duplicate"
            rec["duplicate_of"] = matched_id
            log.debug("Duplicate detected: %s → %s", rec.get("project_id"), matched_id)
        else:
            rec["duplicate_status"] = "unique"
            rec["duplicate_of"] = ""
            # Add to master pool so subsequent records in this batch are checked against it
            master_pool.append(rec)

        processed.append(rec)

    dupes = sum(1 for r in processed if r["duplicate_status"] == "duplicate")
    log.info("Deduplication: %d records, %d duplicates found", len(processed), dupes)
    return processed
