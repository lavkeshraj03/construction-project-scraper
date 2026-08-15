"""app/scrapers/builder_web.py — Builder website / press release collector.

Processes URLs supplied via BUILDER_WEB_URLS in .env.
Extracts project information from publicly accessible builder websites,
project announcement pages, and press releases.

Each URL is fetched and parsed with BeautifulSoup.
For JS-rendered pages, a Playwright fallback is used if available.

IMPORTANT:
- Only processes explicitly configured URLs.
- Does NOT implement a general web crawler.
- Does NOT follow links beyond the supplied page.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.config import settings
from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger
from app.utils.validators import extract_emails, extract_phones

log = get_logger("scraper.builder_web")

# Patterns to find project-relevant text blocks
_PROJ_VALUE_RE = re.compile(
    r"(?:project|contract|tender|cost|value|worth)[^\d₹\$]*[₹\$]?\s*(\d[\d,\.]*\s*(?:cr|crore|lakh|lac|million|billion)?)",
    re.IGNORECASE,
)
_STAGE_KEYWORDS = {
    "under construction", "construction started", "construction begins",
    "construction underway", "construction ongoing", "construction in progress",
    "near completion", "nearing completion", "completed", "inaugurated",
    "launched", "announced", "planned",
}


class BuilderWebScraper(BaseScraper):
    """Scraper for configured builder/project URLs."""

    SOURCE_NAME = "BuilderWeb"

    def run(self) -> list[dict[str, Any]]:
        self.log.info("BuilderWeb scraper starting (limit=%d).", self.limit)
        records: list[dict[str, Any]] = []

        if not settings.BUILDER_WEB_URLS:
            self.log.info(
                "BuilderWeb: No BUILDER_WEB_URLS configured. "
                "Add public builder/project page URLs to .env (BUILDER_WEB_URLS=url1,url2)."
            )
            return records

        for url in settings.BUILDER_WEB_URLS[: self.limit]:
            try:
                rec = self._scrape_page(url)
                if rec:
                    records.append(rec)
            except Exception as exc:
                self.log.error("BuilderWeb URL %s failed: %s", url, exc)

        self.log.info("BuilderWeb scraper finished. Records collected: %d.", len(records))
        return records

    def _scrape_page(self, url: str) -> dict[str, Any] | None:
        self.log.debug("BuilderWeb: fetching %s", url)
        resp = self._get(url)
        if resp is None:
            self.log.warning("BuilderWeb: no response for %s.", url)
            return None

        if "captcha" in resp.text.lower():
            self.log.warning("BuilderWeb: CAPTCHA at %s. Skipping.", url)
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        full_text = soup.get_text(separator=" ", strip=True)

        # Extract fields
        title = self._get_title(soup)
        emails = extract_emails(full_text)
        phones = extract_phones(full_text)
        project_value = self._extract_project_value(full_text)
        stage = self._extract_stage(full_text)
        domain = urlparse(url).netloc

        return {
            "source":        "BuilderWeb",
            "source_url":    url,
            "project_name":  title or "Not Found",
            "builder_name":  domain,
            "location":      "Maharashtra",
            "email":         emails[0] if emails else "Not Found",
            "mobile":        phones[0] if phones else "Not Found",
            "project_value": project_value or "Not Found",
            "current_stage": stage,
            "confidence_score": "Low",
            "raw_data":      full_text[:2000],
        }

    @staticmethod
    def _get_title(soup: BeautifulSoup) -> str | None:
        for tag in ("h1", "h2", "title"):
            el = soup.find(tag)
            if el:
                text = el.get_text(strip=True)
                if len(text) > 5:
                    return text
        return None

    @staticmethod
    def _extract_project_value(text: str) -> str | None:
        match = _PROJ_VALUE_RE.search(text)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _extract_stage(text: str) -> str:
        lower = text.lower()
        for kw in _STAGE_KEYWORDS:
            if kw in lower:
                if "complet" in kw or "inaugurat" in kw:
                    return "Completed"
                if "near" in kw:
                    return "Near Completion"
                if "under" in kw or "ongoing" in kw or "progress" in kw or "underway" in kw or "started" in kw or "begins" in kw:
                    return "Under Construction"
                if "launch" in kw or "announce" in kw or "plan" in kw:
                    return "Planning"
        return "Unknown"
