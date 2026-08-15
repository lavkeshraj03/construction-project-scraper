"""app/scrapers/cppp.py — CPPP (Central Public Procurement Portal) scraper.

Portal: https://etenders.gov.in/eprocure/app

Focuses on construction-related tenders in Maharashtra.
Uses the public search interface.

IMPORTANT: CPPP uses CAPTCHA and JavaScript rendering on many pages.
This scraper targets the publicly accessible search results only.
If CAPTCHA blocks automated access, this adapter logs the issue
and returns an empty list without crashing the pipeline.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper.cppp")

BASE_URL   = "https://etenders.gov.in"
SEARCH_URL = f"{BASE_URL}/eprocure/app"

CONSTRUCTION_KEYWORDS = [
    "construction", "building", "civil work", "infrastructure", "renovation",
    "development", "commercial building", "residential building",
    "hospital construction", "school construction", "office building",
    "flooring", "stone", "granite", "marble",
]

STATE_FILTER = "Maharashtra"


class CPPPScraper(BaseScraper):
    """Scraper for CPPP construction tenders. Graceful if blocked."""

    SOURCE_NAME = "CPPP"

    def run(self) -> list[dict[str, Any]]:
        self.log.info("CPPP scraper starting (limit=%d).", self.limit)
        records: list[dict[str, Any]] = []

        for keyword in CONSTRUCTION_KEYWORDS:
            if len(records) >= self.limit:
                break
            try:
                batch = self._search_keyword(keyword, remaining=self.limit - len(records))
                records.extend(batch)
            except Exception as exc:
                self.log.error("CPPP keyword '%s' failed: %s", keyword, exc)

        # Deduplicate by tender number within this batch
        seen: set[str] = set()
        unique: list[dict] = []
        for r in records:
            key = r.get("tender_number") or r.get("project_name", "")
            if key not in seen:
                seen.add(key)
                unique.append(r)

        self.log.info("CPPP scraper finished. Records collected: %d.", len(unique))
        return unique[: self.limit]

    def _search_keyword(self, keyword: str, remaining: int) -> list[dict[str, Any]]:
        """Search CPPP for a single keyword and return matching tenders."""
        records: list[dict[str, Any]] = []
        params = {
            "page": "FrontEndTendersByOrganisation",
            "service": "page",
            "tendStName": STATE_FILTER,
            "keyword": keyword,
        }
        url = f"{SEARCH_URL}?{urlencode(params)}"
        self.log.debug("CPPP search: keyword='%s'", keyword)

        resp = self._get(url)
        if resp is None:
            self.log.warning("CPPP: no response for keyword '%s'.", keyword)
            return records

        # Check for CAPTCHA / login wall
        if "captcha" in resp.text.lower() or "login" in resp.url.lower():
            self.log.warning(
                "CPPP: CAPTCHA or login required. Automated access not possible for keyword '%s'. "
                "Manual review recommended. URL: %s",
                keyword, resp.url,
            )
            return records

        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select("table.list_table tr") or soup.select("table tr")

        for tr in rows[1:]:  # Skip header row
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue
            rec = self._parse_row(tds)
            if rec:
                records.append(rec)
                if len(records) >= remaining:
                    break

        return records

    def _parse_row(self, tds) -> dict[str, Any] | None:
        try:
            cells = [td.get_text(separator=" ", strip=True) for td in tds]

            # Try to extract a link
            link_tag = tds[0].find("a") or tds[1].find("a")
            source_url = BASE_URL + link_tag["href"] if (link_tag and link_tag.get("href")) else SEARCH_URL

            return {
                "source":        "CPPP",
                "source_url":    source_url,
                "tender_number": cells[0] if cells else "",
                "project_name":  cells[1] if len(cells) > 1 else "",
                "builder_name":  cells[2] if len(cells) > 2 else "",  # Organisation
                "location":      STATE_FILTER,
                "project_value": cells[3] if len(cells) > 3 else "",
                "expected_completion_date": cells[4] if len(cells) > 4 else "",
                "current_stage": "Unknown",
                "confidence_score": "Medium",
            }
        except Exception as exc:
            self.log.debug("CPPP row parse error: %s", exc)
            return None
