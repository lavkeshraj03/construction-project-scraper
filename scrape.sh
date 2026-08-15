#!/bin/bash
# Run the scraper from anywhere.
# Usage:
#   ./scrape.sh             → full run
#   ./scrape.sh --limit 10  → test with 10 records
#   ./scrape.sh --export-only → just refresh Excel

cd "/Users/lavkeshrajput/Desktop/Granite Scrapper/construction-project-scraper"
source .venv/bin/activate
python3 run.py "$@"
