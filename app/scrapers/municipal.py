"""app/scrapers/municipal.py — Municipal building-permission sources adapter.

AUTOMATION STATUS: Partial
-----------------------------
Maharashtra has many municipal corporations (BMC, PMC, NMMC, etc.).
Most of their building-permission portals are:
- JavaScript-heavy (require a browser)
- Behind login walls
- Not publicly accessible via API

This adapter:
1. Accepts a list of public municipal URLs via configuration.
2. Attempts lightweight HTML scraping of each.
3. Logs the reason if a source cannot be automated.
4. Never crashes the pipeline.

Configure via .env:
    MUNICIPAL_URLS=https://bmc.gov.in/...,https://pmc.gov.in/...
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from app.config import settings
from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper.municipal")

# Known public municipal portals with their automation status
KNOWN_PORTALS: dict[str, str] = {
    "https://buildingplan.mcgm.gov.in":
        "MCGM (BMC) building plan portal. Requires login for project data. SKIPPED.",
    "https://pmcmahsauda.com":
        "Pune Municipal — project list may be available without login.",
    "https://www.nmc.gov.in":
        "Nagpur Municipal Corporation. May have public project listings.",
}


class MunicipalScraper(BaseScraper):
    """Generic municipal source adapter."""

    SOURCE_NAME = "Municipal"

    def run(self) -> list[dict[str, Any]]:
        self.log.info("Municipal scraper starting.")
        records: list[dict[str, Any]] = []

        # Log known portals status
        for url, status in KNOWN_PORTALS.items():
            self.log.info("Municipal portal %s — %s", url, status)

        # Process user-configured URLs
        for url in settings.MUNICIPAL_URLS:
            if len(records) >= self.limit:
                break
            try:
                batch = self._scrape_url(url, remaining=self.limit - len(records))
                records.extend(batch)
            except Exception as exc:
                self.log.error("Municipal URL %s failed: %s", url, exc)

        if not settings.MUNICIPAL_URLS:
            self.log.info(
                "Municipal: No MUNICIPAL_URLS configured. "
                "Add public municipal URLs to .env (MUNICIPAL_URLS=url1,url2)."
            )

        self.log.info("Municipal scraper finished. Records collected: %d.", len(records))
        return records

    def _scrape_url(self, url: str, remaining: int) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        self.log.debug("Municipal: fetching %s", url)

        resp = self._get(url)
        if resp is None:
            self.log.warning("Municipal: could not reach %s.", url)
            return records

        if "login" in resp.url.lower() or "signin" in resp.url.lower():
            self.log.warning(
                "Municipal: %s redirected to login page. "
                "Automated access not possible.", url
            )
            return records

        if "captcha" in resp.text.lower():
            self.log.warning("Municipal: CAPTCHA detected at %s.", url)
            return records

        soup = BeautifulSoup(resp.text, "lxml")

        # Generic table extraction
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            headers: list[str] = []
            for tr in rows:
                ths = tr.find_all("th")
                tds = tr.find_all("td")
                if ths and not headers:
                    headers = [th.get_text(strip=True).lower() for th in ths]
                elif tds:
                    rec = self._parse_generic_row(tds, headers, url)
                    if rec:
                        records.append(rec)
                        if len(records) >= remaining:
                            return records

        return records

    def _parse_generic_row(self, tds, headers: list[str], source_url: str) -> dict[str, Any] | None:
        try:
            cells = [td.get_text(separator=" ", strip=True) for td in tds]
            row = dict(zip(headers, cells)) if headers else {}

            proj_name = (
                row.get("project name") or row.get("work name") or
                row.get("description") or (cells[0] if cells else "")
            )
            if not proj_name:
                return None

            link_tag = None
            for td in tds:
                link_tag = td.find("a")
                if link_tag:
                    break

            link = link_tag["href"] if (link_tag and link_tag.get("href")) else source_url
            if link.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(source_url)
                link = f"{parsed.scheme}://{parsed.netloc}{link}"

            return {
                "source":        "Municipal",
                "source_url":    link,
                "project_name":  proj_name,
                "builder_name":  row.get("applicant") or row.get("builder") or "Not Found",
                "location":      row.get("location") or row.get("address") or "Maharashtra",
                "current_stage": row.get("status") or "Unknown",
                "confidence_score": "Low",
            }
        except Exception as exc:
            self.log.debug("Municipal row parse error: %s", exc)
            return None
