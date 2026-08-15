# Phase 1 Construction Project Data Scraper

Lightweight Python scraper that collects **under-construction project data from Maharashtra** via public sources, normalises and deduplicates it, and exports a structured Excel file.

**Primary deliverable:** `output/construction_projects.xlsx`

---

## What It Does

```
Public Sources (MahaRERA / CPPP / GeM / MahaTender / Municipal / Smart City / Builder Web)
    ↓
Scrape relevant construction project data
    ↓
Normalise & clean
    ↓
Deduplicate (RERA / Tender ID → Fuzzy match)
    ↓
Classify materials (Granite / Marble / Quartz / Kota)
    ↓
Score leads (rule-based, 0–100)
    ↓
Optional AI extraction (disabled by default)
    ↓
Store in SQLite
    ↓
Export to Excel (5 sheets)
```

---

## Requirements

- Python 3.11+
- pip

---

## Installation

```bash
cd construction-project-scraper

# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Environment Configuration

Copy the example file and edit as needed:

```bash
cp .env.example .env
```

Key settings in `.env`:

| Variable | Default | Description |
|---|---|---|
| `MAX_PROJECTS_PER_SOURCE` | `100` | Max records scraped per source |
| `REQUEST_DELAY` | `1.0` | Seconds between requests |
| `AI_ENABLED` | `false` | Enable AI extraction (requires API key) |
| `AI_API_KEY` | _(empty)_ | OpenAI / provider API key |
| `ENABLE_MAHARERA` | `true` | Enable MahaRERA scraper |
| `ENABLE_CPPP` | `true` | Enable CPPP scraper |
| `ENABLE_GEM` | `true` | Enable GeM scraper |
| `ENABLE_MAHATENDER` | `true` | Enable Maharashtra e-Tender scraper |
| `ENABLE_MUNICIPAL` | `true` | Enable municipal adapter |
| `ENABLE_SMART_CITY` | `true` | Enable Smart City adapter |
| `ENABLE_BUILDER_WEB` | `true` | Enable builder website collector |
| `BUILDER_WEB_URLS` | _(empty)_ | Comma-separated builder/project page URLs |
| `MUNICIPAL_URLS` | _(empty)_ | Comma-separated public municipal page URLs |

---

## How to Run

### Full run (all sources)
```bash
python run.py
```

### Limit records per source (development/testing)
```bash
python run.py --limit 10
```

### Single source only
```bash
python run.py --source maharera --limit 10
python run.py --source cppp
python run.py --source gem
python run.py --source mahatender
python run.py --source municipal
python run.py --source smart_city
python run.py --source builder_web
```

### Re-export Excel from existing database (no scraping)
```bash
python run.py --export-only
```

### Help
```bash
python run.py --help
```

---

## Test Mode (seed data — no network required)

To verify the complete pipeline locally without scraping:

```bash
python tests/seed_test_data.py
```

This inserts 10 synthetic test records, runs the full normalise → deduplicate → score → export pipeline, and generates `output/construction_projects.xlsx`.

### Unit tests
```bash
python -m pytest tests/test_pipeline.py -v
```

---

## Excel Output

`output/construction_projects.xlsx`

| Sheet | Purpose |
|---|---|
| **Projects** | Main client-facing sheet (frozen header, filters, Excel table, colour-coded stages) |
| **Raw Data** | Source traceability — raw extracted JSON |
| **Sources** | Per-record source metadata |
| **Scrape Log** | Per-run per-source statistics |
| **Summary** | Aggregated counts (stages, priorities, materials, contacts) |

**Required columns in Projects sheet:**
Builder Name, Project Name, Location, Project Value, Decision Maker, Mobile, Email, Architect, Contractor, Builder/Architect/Contractor, Current Stage, Lead Score, Expected Order Value, Competition, Material Required, Material Categories (Granite / Marble / Quartz / Kota), plus supporting metadata.

---

## Supported Sources

| Source | Method | Automation Status |
|---|---|---|
| **MahaRERA** | JSON API + HTML fallback | ✓ Automated (pagination supported) |
| **CPPP** | HTML search | ⚠ May be blocked by CAPTCHA |
| **GeM** | JSON API | ⚠ May require JS rendering |
| **Maharashtra e-Tender** | Form POST | ⚠ May be blocked by CAPTCHA/ASP.NET |
| **Municipal** | Generic HTML table | Configurable URLs; most portals require login |
| **Smart City** | JSON API | ⚠ JS-heavy; national portal queried |
| **Builder Web** | HTML fetch | Configurable URL list only; no crawler |

---

## Known Limitations

1. **CAPTCHA**: CPPP, MahaTender, and some municipal portals use CAPTCHA that cannot be bypassed by this scraper. These sources log a warning and skip gracefully.
2. **JavaScript rendering**: GeM and Smart City portals may require Playwright for full data access. Set `playwright install chromium` and use the Playwright-enabled variant when needed.
3. **MahaRERA API**: The portal's internal API structure may change. If 0 records are returned, check the browser Network tab for the current API endpoint and update `maharera.py`.
4. **Contact information**: Most public sources (RERA, tender portals) do not publish direct mobile/email of decision-makers. These fields will be `Not Found` unless AI enrichment is enabled.
5. **Expected Order Value**: Not calculated by default (`Not Calculated`). Business assumptions are required from the client before implementing a formula.
6. **AI extraction**: Disabled by default. Requires `AI_ENABLED=true` and a valid `AI_API_KEY`.

---

## Project Structure

```
construction-project-scraper/
├── app/
│   ├── config.py            Settings from .env
│   ├── database.py          SQLite persistence (SQLAlchemy)
│   ├── scrapers/
│   │   ├── base.py          Abstract base scraper
│   │   ├── maharera.py      MahaRERA (Priority 1)
│   │   ├── cppp.py          CPPP tenders
│   │   ├── gem.py           GeM bids
│   │   ├── mahatender.py    Maharashtra e-Tender
│   │   ├── municipal.py     Municipal building permissions
│   │   ├── smart_city.py    Smart City portal
│   │   └── builder_web.py   Builder websites
│   ├── processors/
│   │   ├── cleaner.py       Field-level normalisation
│   │   ├── normalizer.py    Full record normalisation
│   │   ├── deduplicator.py  RERA/fuzzy deduplication
│   │   ├── classifier.py    Material + project type classification
│   │   ├── scorer.py        Rule-based lead scoring
│   │   └── ai_extractor.py  Optional LLM enrichment
│   ├── exporters/
│   │   └── excel.py         5-sheet Excel export
│   └── utils/
│       ├── logger.py        Dual file+console logger
│       └── validators.py    Regex validators
├── data/
│   └── projects.db          SQLite database (auto-created)
├── output/
│   └── construction_projects.xlsx   Main deliverable
├── logs/
│   └── scraper.log          Detailed run log
├── tests/
│   ├── test_pipeline.py     Unit tests
│   └── seed_test_data.py    Pipeline verification with synthetic data
├── .env                     Your configuration (not committed)
├── .env.example             Configuration template
├── requirements.txt
├── run.py                   Main entry point
└── README.md
```

---

## Data Quality Rules

- **Never fabricate** names, phones, emails, project values, or contact details.
- Missing values are always `Not Found` or `Unknown` — never invented.
- **Expected Order Value** = `Not Calculated` until client provides an approved formula.
- **Competition** = `Unknown` unless a public source explicitly names a competitor.
- All records preserve `source_url` and `data_collected_at` for full traceability.
- Duplicates are **marked, not deleted** (`duplicate_status = duplicate`).

---

## Lead Scoring Rules

| Condition | Points |
|---|---|
| Current Stage = Under/Advanced/Near Construction | +25 |
| Project Value ≥ ₹1 crore | +25 |
| Material Required = Yes | +20 |
| Decision Maker found | +10 |
| Mobile found | +5 |
| Email found | +5 |
| Architect found | +5 |
| Contractor found | +5 |
| **Maximum** | **100** |

Priority: 80–100 = Very High | 60–79 = High | 40–59 = Medium | 0–39 = Low
