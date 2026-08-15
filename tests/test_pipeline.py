"""tests/test_pipeline.py — Unit tests for core pipeline components.

Run with: python -m pytest tests/ -v
"""

from __future__ import annotations

import pytest
from app.processors.cleaner import (
    clean_currency,
    clean_email,
    clean_name,
    clean_phone,
    clean_pincode,
    clean_stage,
)
from app.processors.classifier import classify_materials
from app.processors.deduplicator import deduplicate
from app.processors.normalizer import normalize
from app.processors.scorer import calculate_lead_score, lead_priority


# ─── Cleaner tests ────────────────────────────────────────────────────────────

class TestCleanName:
    def test_all_caps(self):
        assert clean_name("ABC DEVELOPERS PVT LTD") == "Abc Developers Pvt. Ltd."

    def test_lowercase(self):
        result = clean_name("abc developers")
        assert "Abc" in result

    def test_empty(self):
        assert clean_name("") == "Not Found"

    def test_none(self):
        assert clean_name(None) == "Not Found"


class TestCleanPhone:
    def test_10_digit(self):
        assert clean_phone("9876543210") == "+919876543210"

    def test_with_country_code(self):
        result = clean_phone("+91 98765 43210")
        assert result.startswith("+91")

    def test_empty(self):
        assert clean_phone("") == "Not Found"

    def test_too_short(self):
        assert clean_phone("123") == "Not Found"


class TestCleanEmail:
    def test_normalises_to_lowercase(self):
        assert clean_email("Test@EXAMPLE.COM") == "test@example.com"

    def test_empty(self):
        assert clean_email("") == "Not Found"


class TestCleanCurrency:
    def test_with_symbol(self):
        result = clean_currency("₹50,00,00,000")
        assert "₹" in result

    def test_plain_number(self):
        result = clean_currency("10000000")
        assert "₹" in result

    def test_empty(self):
        assert clean_currency("") == "Not Found"


class TestCleanPincode:
    def test_valid(self):
        assert clean_pincode("411001") == "411001"

    def test_invalid_short(self):
        assert clean_pincode("411") == "Not Found"

    def test_with_spaces(self):
        assert clean_pincode("411 001") == "411001"


class TestCleanStage:
    def test_under_construction(self):
        assert clean_stage("Under Construction") == "Under Construction"
        assert clean_stage("ongoing") == "Under Construction"
        assert clean_stage("ACTIVE") == "Under Construction"

    def test_completed(self):
        assert clean_stage("completed") == "Completed"
        assert clean_stage("Handed Over") == "Completed"

    def test_unknown(self):
        assert clean_stage("") == "Unknown"
        assert clean_stage(None) == "Unknown"


# ─── Normalizer tests ─────────────────────────────────────────────────────────

class TestNormalizer:
    def test_generates_project_id_from_rera(self):
        raw = {
            "source": "MahaRERA",
            "source_url": "https://example.com",
            "rera_number": "P52100012345",
            "project_name": "Test Project",
            "builder_name": "ABC Developers",
        }
        result = normalize(raw)
        assert result["project_id"] == "RERA-P52100012345"

    def test_generates_project_id_from_tender(self):
        raw = {
            "source": "CPPP",
            "source_url": "https://example.com",
            "tender_number": "TND-2024-001",
            "project_name": "Civil Works",
        }
        result = normalize(raw)
        assert result["project_id"] == "TENDER-TND-2024-001"

    def test_generates_project_id_fallback(self):
        raw = {
            "source": "BuilderWeb",
            "source_url": "https://example.com",
            "project_name": "Some Project",
            "location": "Pune",
        }
        result = normalize(raw)
        assert result["project_id"].startswith("PRJ-")

    def test_preserves_raw_data(self):
        raw = {"source": "Test", "project_name": "XYZ"}
        result = normalize(raw)
        assert result["raw_data"] is not None

    def test_sets_bac_composite(self):
        raw = {
            "source": "Test",
            "builder_name": "Alpha Builders",
            "architect": "John Doe",
            "contractor": "Beta Contractors",
        }
        result = normalize(raw)
        assert "Alpha Builders" in result["builder_architect_contractor"]


# ─── Classifier tests ─────────────────────────────────────────────────────────

class TestClassifier:
    def test_granite_detection(self):
        record = {"raw_data": "granite flooring in lobby", "project_name": "Commercial Tower"}
        result = classify_materials(record)
        assert result["material_required"] == "Yes"
        assert "Granite" in result["material_categories"]

    def test_marble_detection(self):
        record = {"raw_data": "italian marble used throughout", "project_name": "Villa"}
        result = classify_materials(record)
        assert "Marble" in result["material_categories"]

    def test_no_material(self):
        record = {"raw_data": "road widening project", "project_name": "Road"}
        result = classify_materials(record)
        assert result["material_required"] in ("Unknown", "No")

    def test_multiple_materials(self):
        record = {"raw_data": "granite facade with marble flooring and kota stone pathway"}
        result = classify_materials(record)
        cats = result["material_categories"]
        assert "Granite" in cats
        assert "Marble" in cats
        assert "Kota" in cats


# ─── Deduplicator tests ───────────────────────────────────────────────────────

class TestDeduplicator:
    def _make_record(self, **kwargs) -> dict:
        base = {
            "project_id": "PRJ-001",
            "rera_number": "",
            "tender_number": "",
            "project_name": "Test Project",
            "builder_name": "ABC Corp",
            "location": "Pune",
            "duplicate_status": "unique",
            "duplicate_of": "",
        }
        base.update(kwargs)
        return base

    def test_rera_match(self):
        existing = [self._make_record(rera_number="P52100012345", project_id="EXISTING")]
        new_rec = [self._make_record(rera_number="P52100012345", project_id="NEW-001")]
        result = deduplicate(new_rec, existing)
        assert result[0]["duplicate_status"] == "duplicate"
        assert result[0]["duplicate_of"] == "EXISTING"

    def test_no_duplicate(self):
        existing = [self._make_record(
            rera_number="P52100099999",
            project_id="EXISTING",
            project_name="Completely Different Building",
            builder_name="Other Builders Ltd",
            location="Nagpur",
        )]
        new_rec = [self._make_record(
            rera_number="P52100012345",
            project_id="NEW-001",
            project_name="Some Unique Tower",
            builder_name="Unique Developers Pvt Ltd",
            location="Mumbai",
        )]
        result = deduplicate(new_rec, existing)
        assert result[0]["duplicate_status"] == "unique"

    def test_fuzzy_duplicate(self):
        existing = [self._make_record(
            project_id="EXISTING",
            project_name="Shreeji Residency Phase 1",
            builder_name="Shreeji Developers",
            location="Pune, Maharashtra",
        )]
        new_rec = [self._make_record(
            project_id="NEW-001",
            project_name="Shreeji Residency Phase-1",
            builder_name="Shreeji Developers Pvt Ltd",
            location="Pune Maharashtra",
        )]
        result = deduplicate(new_rec, existing)
        assert result[0]["duplicate_status"] == "duplicate"

    def test_within_batch_dedup(self):
        new_recs = [
            self._make_record(rera_number="P52100012345", project_id="NEW-001"),
            self._make_record(rera_number="P52100012345", project_id="NEW-002"),
        ]
        result = deduplicate(new_recs, [])
        statuses = [r["duplicate_status"] for r in result]
        assert "unique" in statuses
        assert "duplicate" in statuses


# ─── Scorer tests ─────────────────────────────────────────────────────────────

class TestScorer:
    def _base_record(self) -> dict:
        return {
            "current_stage": "Unknown",
            "project_value": "Not Found",
            "material_required": "Unknown",
            "decision_maker": "Not Found",
            "mobile": "Not Found",
            "email": "Not Found",
            "architect": "Not Found",
            "contractor": "Not Found",
            "lead_score": 0,
        }

    def test_max_score(self):
        rec = {
            "current_stage": "Under Construction",
            "project_value": "50000000",
            "material_required": "Yes",
            "decision_maker": "John Doe",
            "mobile": "+919876543210",
            "email": "john@example.com",
            "architect": "Jane Smith",
            "contractor": "XYZ Builders",
        }
        result = calculate_lead_score(rec)
        assert result["lead_score"] == 100

    def test_zero_score(self):
        rec = self._base_record()
        result = calculate_lead_score(rec)
        assert result["lead_score"] == 0

    def test_under_construction_adds_25(self):
        rec = self._base_record()
        rec["current_stage"] = "Under Construction"
        result = calculate_lead_score(rec)
        assert result["lead_score"] == 25

    def test_lead_priority_very_high(self):
        assert lead_priority(100) == "Very High"
        assert lead_priority(80)  == "Very High"

    def test_lead_priority_high(self):
        assert lead_priority(79) == "High"
        assert lead_priority(60) == "High"

    def test_lead_priority_low(self):
        assert lead_priority(30) == "Low"
        assert lead_priority(0)  == "Low"
