"""run.py — Main entry point.

Usage:
    python run.py                        # Full run (all enabled sources)
    python run.py --limit 10             # Limit each source to 10 records
    python run.py --source maharera      # Run only one source
    python run.py --export-only          # Re-export Excel from existing DB
    python run.py --help                 # Show help

Environment:
    See .env / .env.example for configuration.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Ensure project root is on sys.path ───────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings
from app.database import (
    all_projects,
    all_scrape_runs,
    get_session,
    init_db,
    log_scrape_run,
    upsert_project,
)
from app.exporters.excel import export_to_excel
from app.processors.ai_extractor import enrich_with_ai
from app.processors.classifier import classify_materials, classify_project_type
from app.processors.deduplicator import deduplicate
from app.processors.normalizer import normalize
from app.processors.scorer import calculate_lead_score
from app.utils.logger import get_logger

log = get_logger("run")


# ─── Source registry ──────────────────────────────────────────────────────────

def _get_scrapers(source_filter: str | None, limit: int) -> list[tuple[str, Any]]:
    """Return list of (name, scraper_instance) pairs for enabled sources."""
    from app.scrapers.maharera    import MahaRERAScraper
    from app.scrapers.cppp        import CPPPScraper
    from app.scrapers.gem         import GeMMScraper
    from app.scrapers.mahatender  import MahaTenderScraper
    from app.scrapers.municipal   import MunicipalScraper
    from app.scrapers.smart_city  import SmartCityScraper
    from app.scrapers.builder_web import BuilderWebScraper

    all_scrapers = [
        ("maharera",    settings.ENABLE_MAHARERA,    MahaRERAScraper),
        ("cppp",        settings.ENABLE_CPPP,        CPPPScraper),
        ("gem",         settings.ENABLE_GEM,         GeMMScraper),
        ("mahatender",  settings.ENABLE_MAHATENDER,  MahaTenderScraper),
        ("municipal",   settings.ENABLE_MUNICIPAL,   MunicipalScraper),
        ("smart_city",  settings.ENABLE_SMART_CITY,  SmartCityScraper),
        ("builder_web", settings.ENABLE_BUILDER_WEB, BuilderWebScraper),
    ]

    result = []
    for name, enabled, cls in all_scrapers:
        if source_filter and source_filter.lower() != name:
            continue
        if not enabled and not source_filter:
            log.info("Source '%s' is disabled in config. Skipping.", name)
            continue
        result.append((name, cls(limit=limit)))

    return result


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def run_pipeline(limit: int, source_filter: str | None) -> None:
    run_id = f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    log.info("=" * 60)
    log.info("Construction Project Scraper — %s", run_id)
    log.info("=" * 60)

    # Initialise DB
    init_db()
    session = get_session()

    # Fetch existing records for deduplication
    existing = [
        {c.name: getattr(p, c.name) for c in p.__table__.columns}
        for p in all_projects(session)
    ]

    scrapers = _get_scrapers(source_filter, limit)
    if not scrapers:
        log.warning("No scrapers selected. Check --source argument or .env settings.")

    total_found    = 0
    total_added    = 0
    total_dupes    = 0
    source_summary = {}

    for scraper_name, scraper in scrapers:
        start_time = datetime.now(timezone.utc)
        run_status = "SUCCESS"
        errors     = 0
        found      = 0
        added      = 0
        dupes      = 0

        log.info("── Running scraper: %s ──────────────────────────", scraper_name.upper())
        try:
            raw_records = scraper.run()
            found = len(raw_records)

            # Process each record through the pipeline
            normalised: list[dict] = []
            for raw in raw_records:
                try:
                    rec = normalize(raw)
                    rec = classify_materials(rec)
                    rec = classify_project_type(rec)
                    rec = calculate_lead_score(rec)
                    normalised.append(rec)
                except Exception as exc:
                    log.error("Normalise error for record from %s: %s", scraper_name, exc)
                    errors += 1

            # Deduplicate against existing
            deduped = deduplicate(normalised, existing)

            # Optional AI enrichment
            if settings.AI_ENABLED:
                enriched = []
                for rec in deduped:
                    try:
                        rec = enrich_with_ai(rec, rec.get("raw_data", ""))
                    except Exception as exc:
                        log.error("AI enrichment error: %s", exc)
                    enriched.append(rec)
                deduped = enriched

            # Persist
            for rec in deduped:
                try:
                    is_new, pid = upsert_project(session, rec)
                    if rec.get("duplicate_status") == "duplicate":
                        dupes += 1
                    elif is_new:
                        added += 1
                        existing.append(rec)  # Update pool for next batch
                except Exception as exc:
                    log.error("DB upsert error for %s: %s", rec.get("project_id", "?"), exc)
                    errors += 1

        except Exception as exc:
            log.error("Scraper '%s' raised unhandled exception: %s", scraper_name, exc, exc_info=True)
            run_status = "ERROR"
            errors += 1

        end_time = datetime.now(timezone.utc)

        # Log scraper run
        log_scrape_run(session, {
            "run_id":         run_id,
            "source":         scraper_name,
            "start_time":     start_time,
            "end_time":       end_time,
            "records_found":  found,
            "records_added":  added,
            "duplicates":     dupes,
            "errors":         errors,
            "status":         run_status,
        })

        source_summary[scraper_name] = {
            "found": found, "added": added, "dupes": dupes,
            "errors": errors, "status": run_status,
        }
        total_found += found
        total_added += added
        total_dupes += dupes

        log.info(
            "%s: found=%d  added=%d  dupes=%d  errors=%d  [%s]",
            scraper_name.upper(), found, added, dupes, errors, run_status,
        )

    # Export Excel
    log.info("── Exporting Excel ──────────────────────────────────")
    all_proj   = all_projects(session)
    all_runs   = all_scrape_runs(session)
    excel_path = export_to_excel(all_proj, all_runs)

    # Final summary
    log.info("=" * 60)
    log.info("Construction Project Scraper Completed")
    log.info("")
    log.info("Sources:")
    for name, s in source_summary.items():
        log.info(
            "  %-15s found=%-5d added=%-5d dupes=%-5d [%s]",
            name.upper(), s["found"], s["added"], s["dupes"], s["status"],
        )
    log.info("")
    log.info("Total records found  : %d", total_found)
    log.info("Total records added  : %d", total_added)
    log.info("Total duplicates     : %d", total_dupes)
    log.info("Total in database    : %d", len(all_proj))
    log.info("")
    log.info("Excel: %s", excel_path)
    log.info("=" * 60)

    print("\n" + "=" * 60)
    print("Construction Project Scraper Completed")
    print("")
    print("Sources:")
    for name, s in source_summary.items():
        status_icon = "✓" if s["status"] == "SUCCESS" else "✗"
        print(f"  {status_icon} {name.upper():<15} found={s['found']:<5} added={s['added']:<5} [{s['status']}]")
    print(f"\nTotal in database    : {len(all_proj)}")
    print(f"Excel output         : {excel_path}")
    print("=" * 60 + "\n")


def export_only() -> None:
    """Re-export Excel from existing database without scraping."""
    log.info("Export-only mode: regenerating Excel from existing DB.")
    init_db()
    session = get_session()
    all_proj = all_projects(session)
    all_runs = all_scrape_runs(session)
    path = export_to_excel(all_proj, all_runs)
    print(f"Excel exported: {path} ({len(all_proj)} projects)")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 1 Construction Project Data Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                        # Full run
  python run.py --limit 10             # 10 records per source
  python run.py --source maharera      # Only MahaRERA
  python run.py --source maharera --limit 5
  python run.py --export-only          # Re-export Excel from DB
        """,
    )
    parser.add_argument(
        "--limit", type=int, default=settings.MAX_PROJECTS_PER_SOURCE,
        help=f"Max records per source (default: {settings.MAX_PROJECTS_PER_SOURCE})",
    )
    parser.add_argument(
        "--source", type=str, default=None,
        choices=["maharera", "cppp", "gem", "mahatender", "municipal", "smart_city", "builder_web"],
        help="Run only a specific source",
    )
    parser.add_argument(
        "--export-only", action="store_true",
        help="Re-export Excel from existing database without scraping",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.export_only:
        export_only()
    else:
        run_pipeline(limit=args.limit, source_filter=args.source)
