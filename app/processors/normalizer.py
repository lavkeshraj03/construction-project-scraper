"""app/processors/normalizer.py — Apply all cleaners to a raw record dict."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.processors.cleaner import (
    clean_completion_percentage,
    clean_currency,
    clean_date,
    clean_district,
    clean_email,
    clean_location,
    clean_name,
    clean_phone,
    clean_pincode,
    clean_stage,
    clean_text_field,
)


def _generate_project_id(record: dict[str, Any]) -> str:
    """
    Deterministic ID:
    1. RERA number (best)
    2. Tender number
    3. Source + project_name hash
    """
    if record.get("rera_number"):
        return f"RERA-{record['rera_number'].strip().upper()}"
    if record.get("tender_number"):
        return f"TENDER-{record['tender_number'].strip().upper()}"
    # Fallback — combine source + project_name
    seed = f"{record.get('source', '')}|{record.get('project_name', '')}|{record.get('location', '')}"
    return f"PRJ-{uuid.uuid5(uuid.NAMESPACE_DNS, seed).hex[:12].upper()}"


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Clean and normalise all fields of a raw scraped record.
    Adds project_id.
    Preserves raw_data as JSON blob.
    """
    # Store raw before any modification
    if "raw_data" not in raw or raw["raw_data"] is None:
        raw["raw_data"] = json.dumps({k: v for k, v in raw.items() if k != "raw_data"},
                                     ensure_ascii=False, default=str)

    r: dict[str, Any] = {}

    r["source"]      = clean_text_field(raw.get("source"), "Unknown")
    r["source_url"]  = clean_text_field(raw.get("source_url"), "Not Found")
    r["rera_number"] = clean_text_field(raw.get("rera_number"), "")
    r["tender_number"] = clean_text_field(raw.get("tender_number"), "")

    r["builder_name"]  = clean_name(raw.get("builder_name"))
    r["project_name"]  = clean_name(raw.get("project_name"))
    r["location"]      = clean_location(raw.get("location"))
    r["district"]      = clean_district(raw.get("district"))
    r["pincode"]       = clean_pincode(raw.get("pincode"))
    r["project_value"] = clean_currency(raw.get("project_value"))
    r["project_type"]  = clean_text_field(raw.get("project_type"), "Unknown")

    r["decision_maker"] = clean_text_field(raw.get("decision_maker"), "Not Found")
    r["mobile"]         = clean_phone(raw.get("mobile"))
    r["email"]          = clean_email(raw.get("email"))
    r["architect"]      = clean_text_field(raw.get("architect"), "Not Found")
    r["contractor"]     = clean_text_field(raw.get("contractor"), "Not Found")

    # Composite field
    bac_parts = [
        r["builder_name"] if r["builder_name"] != "Not Found" else None,
        r["architect"]    if r["architect"]    != "Not Found" else None,
        r["contractor"]   if r["contractor"]   != "Not Found" else None,
    ]
    r["builder_architect_contractor"] = " / ".join(p for p in bac_parts if p) or "Not Found"

    r["current_stage"]           = clean_stage(raw.get("current_stage"))
    r["completion_percentage"]   = clean_completion_percentage(raw.get("completion_percentage"))
    r["expected_completion_date"] = clean_date(raw.get("expected_completion_date"))

    # Lead intelligence — set by processors
    r["lead_score"]           = raw.get("lead_score")
    r["expected_order_value"] = raw.get("expected_order_value", "Not Calculated")
    r["competition"]          = clean_text_field(raw.get("competition"), "Unknown")

    # Material
    r["material_required"]   = clean_text_field(raw.get("material_required"), "Unknown")
    r["material_categories"] = clean_text_field(raw.get("material_categories"), "")

    # Quality
    r["confidence_score"] = clean_text_field(raw.get("confidence_score"), "Low")

    # Dedup — default until deduplicator runs
    r["duplicate_status"] = raw.get("duplicate_status", "unique")
    r["duplicate_of"]     = raw.get("duplicate_of", "")

    r["raw_data"] = raw["raw_data"]

    # Generate stable project ID
    r["project_id"] = _generate_project_id(r)

    return r
