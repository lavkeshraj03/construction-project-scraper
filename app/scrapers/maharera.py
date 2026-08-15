"""app/scrapers/maharera.py — MahaRERA public search scraper (Priority 1).

MahaRERA public portal: https://maharera.maharashtra.gov.in/

The portal renders project cards at:
    https://maharera.maharashtra.gov.in/projects-search-result

Each card has class: row shadow p-3 mb-5 bg-body rounded

The scraper:
1. Fetches the search results page (GET, paginated via POST form).
2. Parses project cards from HTML.
3. Optionally fetches individual project detail pages.
4. Handles pagination via form POST.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper.maharera")

BASE_URL         = "https://maharera.maharashtra.gov.in"
SEARCH_URL       = f"{BASE_URL}/projects-search-result"
DETAIL_BASE      = "https://maharerait.maharashtra.gov.in/public/project/view"
PAGE_SIZE        = 10   # MahaRERA appears to show ~10 per page


class MahaRERAScraper(BaseScraper):
    """Scrapes MahaRERA for publicly listed Maharashtra construction projects."""

    SOURCE_NAME = "MahaRERA"

    def run(self) -> list[dict[str, Any]]:
        self.log.info("MahaRERA scraper starting (limit=%d).", self.limit)
        records: list[dict[str, Any]] = []

        try:
            records = self._scrape_listing()
        except Exception as exc:
            self.log.error("MahaRERA scraper failed: %s", exc, exc_info=True)

        self.log.info("MahaRERA scraper finished. Records collected: %d.", len(records))
        return records

    # ─── Main scraping method ─────────────────────────────────────────────────

    def _scrape_listing(self) -> list[dict[str, Any]]:
        """
        Fetch and parse the MahaRERA project listing page.
        The first GET returns the default listing.
        Subsequent pages are fetched via POST with pagination parameters.
        """
        records: list[dict[str, Any]] = []
        page = 0

        # First fetch — GET (default page)
        self.log.debug("Fetching MahaRERA listing page 0: %s", SEARCH_URL)
        resp = self._get(SEARCH_URL)
        if resp is None:
            self.log.warning("MahaRERA: cannot reach %s.", SEARCH_URL)
            return records

        soup = BeautifulSoup(resp.text, "lxml")

        # Extract form tokens for POST pagination
        hidden: dict[str, str] = {}
        form = soup.find("form", id=re.compile(r"projects-search"))
        if form:
            for inp in form.find_all("input", {"type": "hidden"}):
                name = inp.get("name", "")
                val  = inp.get("value", "")
                if name:
                    hidden[name] = val

        # Parse page 0
        batch = self._parse_cards(soup)
        records.extend(batch)

        if len(records) >= self.limit:
            return records[: self.limit]

        # Paginate via POST
        while len(records) < self.limit:
            page += 1
            self.log.debug("Fetching MahaRERA listing page %d …", page)
            payload = {
                **hidden,
                "page": str(page),
            }
            resp = self._post(SEARCH_URL, data=payload)
            if resp is None:
                self.log.warning("MahaRERA: no response on POST page %d.", page)
                break

            soup = BeautifulSoup(resp.text, "lxml")
            batch = self._parse_cards(soup)
            if not batch:
                self.log.info("MahaRERA: no more results at page %d.", page)
                break
            records.extend(batch)

            # Update hidden form tokens from the new page
            form = soup.find("form", id=re.compile(r"projects-search"))
            if form:
                for inp in form.find_all("input", {"type": "hidden"}):
                    name = inp.get("name", "")
                    val  = inp.get("value", "")
                    if name:
                        hidden[name] = val

        return records[: self.limit]

    def _parse_cards(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Extract project records from all project cards on a results page."""
        records: list[dict[str, Any]] = []

        # Project cards have class: row shadow p-3 mb-5 bg-body rounded
        cards = soup.find_all("div", class_=lambda c: c and "shadow" in c and "row" in c)

        for card in cards:
            rec = self._parse_card(card)
            if rec:
                records.append(rec)

        self.log.debug("MahaRERA: parsed %d cards.", len(records))
        return records

    def _parse_card(self, card) -> dict[str, Any] | None:
        """Parse a single project card div into a raw record dict."""
        try:
            text = card.get_text(separator="|", strip=True)

            # RERA number — format: P followed by digits
            rera_match = re.search(r"#\s*(P\d[\w]+)", text)
            rera_num = rera_match.group(1) if rera_match else ""

            # Project name — line after RERA number (before builder name)
            lines = [l.strip() for l in text.split("|") if l.strip() and l.strip() != "#"]
            lines = [l for l in lines if l]  # remove empty

            # Identify lines
            proj_name   = ""
            builder     = ""
            location    = ""
            district    = ""
            pincode     = ""
            state       = ""
            last_modified = ""

            # The card has a predictable structure after RERA:
            # # RERA | PROJECT NAME | BUILDER | LOCATION | ...
            rera_idx = next((i for i, l in enumerate(lines) if re.match(r"P\d", l)), None)
            if rera_idx is not None:
                remaining = lines[rera_idx + 1:]
                # First non-label line is project name
                skip_labels = {
                    "state", "maharashtra", "pincode", "certificate", "district",
                    "last modified", "extension certificate", "n/a", "find route",
                    "view details", "view original application", "application",
                }
                content_lines = [l for l in remaining if l.lower() not in skip_labels]
                if content_lines:
                    proj_name = content_lines[0] if len(content_lines) > 0 else ""
                    builder   = content_lines[1] if len(content_lines) > 1 else ""
                    location  = content_lines[2] if len(content_lines) > 2 else ""

            # Extract labeled fields
            label_map: dict[str, str] = {}
            for i, line in enumerate(lines):
                lower = line.lower()
                if lower in ("state", "pincode", "district", "last modified", "certificate"):
                    if i + 1 < len(lines):
                        label_map[lower] = lines[i + 1]

            district  = label_map.get("district", "")
            pincode   = label_map.get("pincode", "")
            state     = label_map.get("state", "")
            last_modified = label_map.get("last modified", "")

            # Source URL — from View Details link
            view_link = card.find("a", string=re.compile(r"View Details", re.IGNORECASE))
            source_url = view_link["href"] if view_link and view_link.get("href") else SEARCH_URL

            if not rera_num and not proj_name:
                return None

            return {
                "source":        "MahaRERA",
                "source_url":    source_url,
                "rera_number":   rera_num,
                "project_name":  proj_name,
                "builder_name":  builder,
                "location":      location,
                "district":      district,
                "pincode":       pincode,
                "current_stage": "Unknown",   # Status not shown on listing; would need detail page
                "expected_completion_date": last_modified,
                "confidence_score": "High",
            }

        except Exception as exc:
            self.log.debug("MahaRERA card parse error: %s", exc)
            return None

    @staticmethod
    def _strip_html(text: Any) -> str:
        if not text:
            return ""
        return BeautifulSoup(str(text), "lxml").get_text(strip=True)
