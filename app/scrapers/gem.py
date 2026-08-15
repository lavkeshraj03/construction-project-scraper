"""app/scrapers/gem.py — GeM (Government e-Marketplace) scraper.

Portal: https://gem.gov.in

Focuses on construction/material-related bids and orders.

AUTOMATION NOTE:
GeM uses heavy JavaScript rendering. The public search endpoint
returns JSON that we can query directly. If this changes,
the scraper logs the issue and continues.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper.gem")

BASE_URL   = "https://gem.gov.in"
# GeM public bid search — fetched via XHR in the browser
# Note: GeM is heavily JS-rendered. This URL may require periodic update.
BID_API    = "https://gem.gov.in/api/bids/search"
# Fallback HTML search
SEARCH_URL = "https://gem.gov.in/bids/search"

GEM_KEYWORDS = [
    "granite", "marble", "quartz", "kota stone",
    "flooring", "civil construction", "building construction",
]

STATE_FILTER = "Maharashtra"



class GeMMScraper(BaseScraper):
    """Scraper for GeM construction/material bids."""

    SOURCE_NAME = "GeM"

    def run(self) -> list[dict[str, Any]]:
        self.log.info("GeM scraper starting (limit=%d).", self.limit)
        records: list[dict[str, Any]] = []

        for keyword in GEM_KEYWORDS:
            if len(records) >= self.limit:
                break
            try:
                batch = self._search_keyword(keyword, remaining=self.limit - len(records))
                records.extend(batch)
            except Exception as exc:
                self.log.error("GeM keyword '%s' failed: %s", keyword, exc)

        # Deduplicate by bid number
        seen: set[str] = set()
        unique: list[dict] = []
        for r in records:
            key = r.get("tender_number") or r.get("project_name", "")
            if key not in seen:
                seen.add(key)
                unique.append(r)

        self.log.info("GeM scraper finished. Records collected: %d.", len(unique))
        return unique[: self.limit]

    def _search_keyword(self, keyword: str, remaining: int) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        params = {
            "searchedKeyword": keyword,
            "page":            1,
            "state":           STATE_FILTER,
        }
        url = f"{BID_API}?{urlencode(params)}"
        self.log.debug("GeM search: keyword='%s'", keyword)

        resp = self._get(url)
        if resp is None:
            self.log.warning("GeM: no response for keyword '%s'.", keyword)
            return records

        # Try JSON response
        try:
            data = resp.json()
        except Exception:
            # Check for JS-rendered page or CAPTCHA
            if "captcha" in resp.text.lower():
                self.log.warning(
                    "GeM: CAPTCHA detected. Automated access blocked for keyword '%s'. "
                    "Consider using Playwright for this source.",
                    keyword,
                )
            else:
                self.log.warning("GeM: response is not JSON for keyword '%s'.", keyword)
            return records

        bids = data.get("data") or data.get("bids") or data.get("results") or []
        if isinstance(bids, dict):
            bids = list(bids.values())

        for item in bids[:remaining]:
            rec = self._parse_bid(item)
            if rec:
                records.append(rec)

        return records

    def _parse_bid(self, item: Any) -> dict[str, Any] | None:
        try:
            if not isinstance(item, dict):
                return None

            bid_num  = item.get("bid_number") or item.get("bidNumber") or item.get("id") or ""
            title    = item.get("title") or item.get("itemName") or item.get("name") or ""
            org      = item.get("organisation") or item.get("buyerName") or item.get("ministry") or ""
            state    = item.get("state") or STATE_FILTER
            value    = item.get("estimatedAmount") or item.get("value") or item.get("amount") or ""
            end_date = item.get("endDate") or item.get("bidEndDate") or ""
            bid_url  = item.get("url") or f"{BASE_URL}/bid/{bid_num}" if bid_num else BASE_URL

            return {
                "source":        "GeM",
                "source_url":    bid_url,
                "tender_number": str(bid_num),
                "project_name":  title,
                "builder_name":  org,
                "location":      state,
                "project_value": str(value),
                "expected_completion_date": str(end_date),
                "current_stage": "Unknown",
                "confidence_score": "Medium",
            }
        except Exception as exc:
            self.log.debug("GeM bid parse error: %s | item=%s", exc, item)
            return None
