"""tests/seed_test_data.py — Insert realistic test records to verify the full pipeline.

Run standalone:
    python tests/seed_test_data.py

This does NOT make any network requests. It verifies that:
1. Database initialises correctly.
2. Normalizer processes records.
3. Deduplicator marks duplicates.
4. Excel exporter generates a valid file.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_session, init_db, upsert_project, all_projects, all_scrape_runs, log_scrape_run
from app.exporters.excel import export_to_excel
from app.processors.classifier import classify_materials, classify_project_type
from app.processors.deduplicator import deduplicate
from app.processors.normalizer import normalize
from app.processors.scorer import calculate_lead_score
from datetime import datetime, timezone

# ─── Seed records (realistic but synthetic — NOT real project data) ───────────

SEED_RECORDS = [
    {
        "source":        "MahaRERA",
        "source_url":    "https://maharera.maharashtra.gov.in/project/view/P52100001234",
        "rera_number":   "P52100001234",
        "builder_name":  "SHREEJI DEVELOPERS PVT LTD",
        "project_name":  "Shreeji Residency Phase 1",
        "location":      "Baner, Pune",
        "district":      "Pune",
        "pincode":       "411045",
        "project_value": "45,00,00,000",
        "decision_maker":"Rajesh Mehta",
        "mobile":        "9876543210",
        "email":         "rajesh@shreeji.com",
        "architect":     "Ar. Sunil Joshi",
        "contractor":    "Not Found",
        "current_stage": "Under Construction",
        "completion_percentage": 45.0,
        "expected_completion_date": "March 2026",
        "project_type":  "Residential",
        "confidence_score": "High",
    },
    {
        "source":        "MahaRERA",
        "source_url":    "https://maharera.maharashtra.gov.in/project/view/P52100005678",
        "rera_number":   "P52100005678",
        "builder_name":  "Godrej Properties Ltd",
        "project_name":  "Godrej Nature Plus",
        "location":      "Hinjewadi, Pune",
        "district":      "Pune",
        "pincode":       "411057",
        "project_value": "120,00,00,000",
        "decision_maker":"Not Found",
        "mobile":        "Not Found",
        "email":         "pune@godrej.com",
        "architect":     "Not Found",
        "contractor":    "Not Found",
        "current_stage": "Advanced Construction",
        "completion_percentage": 75.0,
        "expected_completion_date": "December 2025",
        "project_type":  "Residential",
        "confidence_score": "High",
    },
    {
        "source":        "CPPP",
        "source_url":    "https://etenders.gov.in/eprocure/app?tender=TND2024001",
        "tender_number": "TND/2024/MH/001",
        "builder_name":  "Public Works Department Maharashtra",
        "project_name":  "Construction of Government Office Building Nagpur",
        "location":      "Nagpur",
        "district":      "Nagpur",
        "pincode":       "440001",
        "project_value": "85,00,00,000",
        "decision_maker":"Not Found",
        "mobile":        "Not Found",
        "email":         "Not Found",
        "architect":     "Not Found",
        "contractor":    "Not Found",
        "current_stage": "Approved",
        "confidence_score": "Medium",
    },
    {
        "source":        "GeM",
        "source_url":    "https://gem.gov.in/bid/GEM20240001",
        "tender_number": "GEM/2024/B/001",
        "builder_name":  "Municipal Corporation of Greater Mumbai",
        "project_name":  "Supply and Laying of Granite Flooring - BMC Office",
        "location":      "Mumbai",
        "district":      "Mumbai",
        "pincode":       "400001",
        "project_value": "2,50,00,000",
        "material_required": "Yes",
        "material_categories": "Granite",
        "current_stage": "Under Construction",
        "confidence_score": "Medium",
    },
    {
        "source":        "MahaTender",
        "source_url":    "https://mahatenders.gov.in/tender/TND2024MH002",
        "tender_number": "MHT/2024/CIVIL/002",
        "builder_name":  "Nashik Municipal Corporation",
        "project_name":  "Renovation of Municipal Market with Marble and Kota Flooring",
        "location":      "Nashik",
        "district":      "Nashik",
        "pincode":       "422001",
        "project_value": "3,75,00,000",
        "current_stage": "Under Construction",
        "confidence_score": "Medium",
    },
    {
        "source":        "SmartCity",
        "source_url":    "https://smartcities.gov.in/project/pune/001",
        "builder_name":  "Pune Smart City Mission",
        "project_name":  "Smart Roads and Public Spaces Development Phase 2",
        "location":      "Pune",
        "district":      "Pune",
        "project_value": "200,00,00,000",
        "current_stage": "Under Construction",
        "confidence_score": "Medium",
    },
    {
        "source":        "BuilderWeb",
        "source_url":    "https://lodhagroup.com/projects/lodha-park-nagpur",
        "builder_name":  "Lodha Group",
        "project_name":  "Lodha Park Nagpur",
        "location":      "Nagpur, Maharashtra",
        "district":      "Nagpur",
        "project_value": "500,00,00,000",
        "architect":     "HafizContractor Architects",
        "current_stage": "Under Construction",
        "completion_percentage": 30.0,
        "confidence_score": "Low",
    },
    {
        "source":        "MahaRERA",
        "source_url":    "https://maharera.maharashtra.gov.in/project/view/P52100009999",
        "rera_number":   "P52100009999",
        "builder_name":  "Kalpataru Ltd",
        "project_name":  "Kalpataru Splendour",
        "location":      "Thane West",
        "district":      "Thane",
        "pincode":       "400601",
        "project_value": "90,00,00,000",
        "current_stage": "Near Completion",
        "completion_percentage": 90.0,
        "expected_completion_date": "June 2025",
        "confidence_score": "High",
    },
    {
        "source":        "Municipal",
        "source_url":    "https://pmc.gov.in/building-permissions/12345",
        "builder_name":  "Rohan Developers",
        "project_name":  "Rohan Mithila Commercial Complex",
        "location":      "Kothrud, Pune",
        "district":      "Pune",
        "pincode":       "411038",
        "project_value": "35,00,00,000",
        "architect":     "Ar. Priya Kulkarni",
        "current_stage": "Approved",
        "confidence_score": "Low",
    },
    # Intentional duplicate of record 0 (same RERA number)
    {
        "source":        "BuilderWeb",
        "source_url":    "https://shreeji.com/projects/residency-phase1",
        "rera_number":   "P52100001234",   # Same RERA → duplicate
        "builder_name":  "Shreeji Developers",
        "project_name":  "Shreeji Residency",
        "location":      "Baner Pune",
        "current_stage": "Under Construction",
        "confidence_score": "Low",
    },
]


def main() -> None:
    print("Seeding test data into database …")
    init_db()
    session = get_session()

    existing = [
        {c.name: getattr(p, c.name) for c in p.__table__.columns}
        for p in all_projects(session)
    ]

    # Normalise all
    normalised = []
    for raw in SEED_RECORDS:
        rec = normalize(raw)
        rec = classify_materials(rec)
        rec = classify_project_type(rec)
        rec = calculate_lead_score(rec)
        normalised.append(rec)

    # Deduplicate
    deduped = deduplicate(normalised, existing)

    # Persist
    added = 0
    dupes = 0
    for rec in deduped:
        is_new, pid = upsert_project(session, rec)
        if rec["duplicate_status"] == "duplicate":
            dupes += 1
            print(f"  DUPLICATE  {pid}")
        elif is_new:
            added += 1
            print(f"  INSERTED   {pid}")
        else:
            print(f"  UPDATED    {pid}")

    # Add a seed scrape run log entry
    log_scrape_run(session, {
        "run_id":        "RUN-SEED-001",
        "source":        "seed_data",
        "start_time":    datetime.now(timezone.utc),
        "end_time":      datetime.now(timezone.utc),
        "records_found": len(SEED_RECORDS),
        "records_added": added,
        "duplicates":    dupes,
        "errors":        0,
        "status":        "SUCCESS",
    })

    # Export Excel
    all_proj = all_projects(session)
    all_runs = all_scrape_runs(session)
    excel_path = export_to_excel(all_proj, all_runs)

    print(f"\n✓ Database:  {len(all_proj)} total projects ({added} new, {dupes} duplicates)")
    print(f"✓ Excel:     {excel_path}")
    print("\nSeed data complete. Open the Excel file to verify the output.")


if __name__ == "__main__":
    main()
