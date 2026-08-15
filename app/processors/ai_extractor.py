"""app/processors/ai_extractor.py — Optional AI-assisted extraction.

Only called when:
1. AI_ENABLED=true in .env
2. The caller explicitly requests enrichment for a specific field set.

The AI must return strict JSON matching the EXTRACTION_SCHEMA.
If the AI returns unexpected data, we fall back to "Not Found"/"Unknown".

IMPORTANT: AI never invents data. Every AI-returned value is labeled
confidence_score = "Medium" (or "Low" if uncertain).
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("ai_extractor")

EXTRACTION_SCHEMA = {
    "builder_name": "",
    "project_name": "",
    "location": "",
    "project_value": "",
    "decision_maker": "",
    "mobile": "",
    "email": "",
    "architect": "",
    "contractor": "",
    "builder_architect_contractor": "",
    "current_stage": "",
    "material_required": "",
    "material_categories": "",
}

_ALLOWED_VALUES_MATERIAL_REQUIRED = {"Yes", "No", "Unknown"}
_ALLOWED_STAGES = {
    "Planning", "Approved", "Pre-Construction", "Under Construction",
    "Advanced Construction", "Near Completion", "Completed", "Unknown",
}


def _clean_ai_response(raw_text: str) -> dict[str, Any]:
    """Extract JSON block from AI text response."""
    # Try to extract JSON from markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if match:
        raw_text = match.group(1)
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        log.warning("AI response is not valid JSON; skipping enrichment.")
        return {}

    # Validate and sanitise
    result: dict[str, Any] = {}
    for key in EXTRACTION_SCHEMA:
        val = data.get(key, "")
        if not isinstance(val, str):
            val = str(val)
        val = val.strip()
        if not val:
            val = "Not Found" if key != "material_categories" else ""
        result[key] = val

    # Enforce allowed values
    if result.get("material_required") not in _ALLOWED_VALUES_MATERIAL_REQUIRED:
        result["material_required"] = "Unknown"
    if result.get("current_stage") not in _ALLOWED_STAGES:
        result["current_stage"] = "Unknown"

    return result


def _call_openai(prompt: str) -> str:
    """Call OpenAI chat completions API."""
    try:
        import httpx  # type: ignore

        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.AI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.AI_MODEL,
                "messages": [
                    {"role": "system", "content": (
                        "You are a construction project data extraction assistant. "
                        "Extract structured information from the given text and return ONLY valid JSON. "
                        "Never invent information. Use 'Not Found' if a field is unavailable."
                    )},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": 512,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        log.error("OpenAI API call failed: %s", exc)
        return ""


def enrich_with_ai(record: dict[str, Any], raw_text: str) -> dict[str, Any]:
    """
    Attempt AI extraction from raw_text.
    Only called when AI_ENABLED=true.
    Merges results into record without overwriting already-found values.
    """
    if not settings.AI_ENABLED:
        return record

    if not settings.AI_API_KEY:
        log.warning("AI_ENABLED=true but AI_API_KEY is empty; skipping.")
        return record

    prompt = (
        "Extract construction project information from the text below.\n"
        "Return ONLY a JSON object with these keys:\n"
        f"{json.dumps(list(EXTRACTION_SCHEMA.keys()), indent=2)}\n\n"
        "Rules:\n"
        "- Use 'Not Found' for any field you cannot find.\n"
        "- Use 'Unknown' only for ambiguous categorical fields.\n"
        "- NEVER invent phone numbers, emails, names, or project values.\n"
        "- material_required must be: Yes, No, or Unknown\n"
        "- current_stage must be one of: Planning, Approved, Pre-Construction, "
        "Under Construction, Advanced Construction, Near Completion, Completed, Unknown\n\n"
        f"TEXT:\n{raw_text[:3000]}"
    )

    if settings.AI_PROVIDER.lower() == "openai":
        raw_response = _call_openai(prompt)
    else:
        log.warning("AI provider '%s' not implemented; skipping.", settings.AI_PROVIDER)
        return record

    if not raw_response:
        return record

    extracted = _clean_ai_response(raw_response)
    if not extracted:
        return record

    # Merge: only fill fields that are currently placeholder values
    placeholders = {"Not Found", "Unknown", "", None}
    merged = record.copy()
    for key, val in extracted.items():
        if merged.get(key) in placeholders and val not in ("Not Found", "Unknown", ""):
            merged[key] = val

    # Mark as AI-enriched (lower confidence)
    if merged.get("confidence_score") == "High":
        merged["confidence_score"] = "Medium"
    elif not merged.get("confidence_score"):
        merged["confidence_score"] = "Low"

    log.debug("AI enrichment applied to project_id=%s", record.get("project_id"))
    return merged
