"""app/scrapers/mahatender.py — Maharashtra e-Tender portal scraper.

Portal: https://mahatenders.gov.in

Targets construction-related tenders in Maharashtra.

AUTOMATION NOTE:
The portal uses ASP.NET session tokens for search forms.
Direct POST-based search requires an active session cookie.
This scraper attempts to:
1. Fetch the search page to get session cookies.
2. Submit a search form with a construction keyword.
3. Parse results.

If blocked by the portal, the scraper logs the reason and returns
empty results — it does NOT crash the pipeline.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper.mahatender")

BASE_URL   = "https://mahatenders.gov.in"
SEARCH_URL = f"{BASE_URL}/nicgep/app"

CONSTRUCTION_KEYWORDS = [
    "construction", "civil work", "building", "renovation",
    "infrastructure", "flooring", "granite", "marble", "stone", "development",
]


class MahaTenderScraper(BaseScraper):
    """Scraper for Maharashtra e-Tender portal."""

    SOURCE_NAME = "MahaTender"

    def run(self) -> list[dict[str, Any]]:
        self.log.info("MahaTender scraper starting (limit=%d).", self.limit)
        records: list[dict[str, Any]] = []

        try:
            records = self._scrape()
        except Exception as exc:
            self.log.error("MahaTender scraper failed: %s", exc, exc_info=True)

        self.log.info("MahaTender scraper finished. Records collected: %d.", len(records))
        return records

    def _scrape(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []

        # Step 1: Get the search page (to acquire session)
        resp = self._get(SEARCH_URL)
        if resp is None:
            self.log.warning(
                "MahaTender: cannot reach %s. Source will be skipped. "
                "Verify the portal URL is reachable.", SEARCH_URL
            )
            return records

        if "captcha" in resp.text.lower() or len(resp.text) < 500:
            self.log.warning(
                "MahaTender: CAPTCHA or empty response detected. "
                "Automated access may require Playwright. Skipping source."
            )
            return records

        soup = BeautifulSoup(resp.text, "lxml")

        # Extract hidden form fields (ASP.NET ViewState etc.)
        form = soup.find("form")
        hidden_fields: dict[str, str] = {}
        if form:
            for inp in form.find_all("input", {"type": "hidden"}):
                name = inp.get("name", "")
                val  = inp.get("value", "")
                if name:
                    hidden_fields[name] = val

        for keyword in CONSTRUCTION_KEYWORDS:
            if len(records) >= self.limit:
                break
            try:
                batch = self._search_keyword(keyword, hidden_fields, remaining=self.limit - len(records))
                records.extend(batch)
            except Exception as exc:
                self.log.error("MahaTender keyword '%s' failed: %s", keyword, exc)

        # Deduplicate within batch
        seen: set[str] = set()
        unique: list[dict] = []
        for r in records:
            key = r.get("tender_number") or r.get("project_name", "")
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique[: self.limit]

    def _search_keyword(
        self, keyword: str, hidden: dict[str, str], remaining: int
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        payload = {
            **hidden,
            "keyword": keyword,
            "tenderType": "all",
        }

        self.log.debug("MahaTender search: keyword='%s'", keyword)
        resp = self._post(SEARCH_URL, data=payload)
        if resp is None:
            self.log.warning("MahaTender: no response for keyword '%s'.", keyword)
            return records

        if "captcha" in resp.text.lower():
            self.log.warning(
                "MahaTender: CAPTCHA after POST for keyword '%s'. "
                "Skipping this keyword.", keyword
            )
            return records

        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select("table tr") or []

        for tr in rows[1:]:
            tds = tr.find_all("td")
            if len(tds) < 3:
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
            link_tag = None
            for td in tds:
                link_tag = td.find("a")
                if link_tag:
                    break

            source_url = BASE_URL + link_tag["href"] if (link_tag and link_tag.get("href")) else SEARCH_URL

            return {
                "source":        "MahaTender",
                "source_url":    source_url,
                "tender_number": cells[0] if cells else "",
                "project_name":  cells[1] if len(cells) > 1 else "",
                "builder_name":  cells[2] if len(cells) > 2 else "",
                "location":      "Maharashtra",
                "project_value": cells[3] if len(cells) > 3 else "",
                "expected_completion_date": cells[4] if len(cells) > 4 else "",
                "current_stage": "Unknown",
                "confidence_score": "Medium",
            }
        except Exception as exc:
            self.log.debug("MahaTender row parse error: %s", exc)
            return None
