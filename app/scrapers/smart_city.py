"""app/scrapers/smart_city.py — Smart City portal adapter.

AUTOMATION STATUS: Partial
-----------------------------
India's Smart City Mission portals vary by city.
Most Smart City dashboards are JavaScript-rendered and do not
expose machine-readable project data publicly.

This adapter:
1. Targets the Smart City Mission portal project list.
2. Falls back to the national Smart City portal CSV/API if available.
3. Logs automation blockers without crashing.

Smart Cities in Maharashtra:
Pune, Nagpur, Aurangabad (Chhatrapati Sambhajinagar), Solapur,
Nashik, Amravati, Kalyan-Dombivli, Thane, Pimpri-Chinchwad

National portal: https://smartcities.gov.in/city_data/
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper.smart_city")

NATIONAL_PORTAL = "https://smartcities.gov.in"
PROJECTS_API    = f"{NATIONAL_PORTAL}/city_data/projects.json"

MAHARASHTRA_CITIES = [
    "Pune", "Nagpur", "Aurangabad", "Solapur",
    "Nashik", "Amravati", "Kalyan-Dombivli", "Thane", "Pimpri-Chinchwad",
]


class SmartCityScraper(BaseScraper):
    """Smart City portal adapter — national project list + city pages."""

    SOURCE_NAME = "SmartCity"

    def run(self) -> list[dict[str, Any]]:
        self.log.info("SmartCity scraper starting (limit=%d).", self.limit)
        records: list[dict[str, Any]] = []

        try:
            records = self._fetch_national_api()
        except Exception as exc:
            self.log.error("SmartCity national API failed: %s", exc)

        if not records:
            self.log.info(
                "SmartCity: national API returned 0 records. "
                "The portal may require JavaScript (Playwright) for full data access. "
                "Consider enabling Playwright for this source in future."
            )

        self.log.info("SmartCity scraper finished. Records collected: %d.", len(records))
        return records[: self.limit]

    def _fetch_national_api(self) -> list[dict[str, Any]]:
        """Attempt to fetch JSON project list from national Smart City portal."""
        records: list[dict[str, Any]] = []
        resp = self._get(PROJECTS_API)
        if resp is None:
            self.log.warning("SmartCity: could not reach %s.", PROJECTS_API)
            return records

        try:
            data = resp.json()
        except Exception:
            self.log.warning("SmartCity: response is not JSON. HTML scrape fallback.")
            return self._scrape_html(resp.text)

        items = data if isinstance(data, list) else data.get("projects") or data.get("data") or []
        for item in items:
            if not isinstance(item, dict):
                continue
            city = item.get("city") or item.get("cityName") or ""
            if not any(c.lower() in city.lower() for c in MAHARASHTRA_CITIES):
                continue  # Filter to Maharashtra only
            rec = self._parse_project(item)
            if rec:
                records.append(rec)

        return records

    def _scrape_html(self, html: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(".project-card, .project-item, article.project")
        for card in cards:
            title = card.find(["h2", "h3", "h4"])
            if not title:
                continue
            link = card.find("a")
            records.append({
                "source":       "SmartCity",
                "source_url":   NATIONAL_PORTAL + (link["href"] if link else ""),
                "project_name": title.get_text(strip=True),
                "builder_name": "Smart Cities Mission",
                "location":     "Maharashtra",
                "current_stage": "Unknown",
                "confidence_score": "Low",
            })
        return records

    def _parse_project(self, item: dict) -> dict[str, Any] | None:
        try:
            proj_name = item.get("project") or item.get("title") or item.get("name") or ""
            if not proj_name:
                return None
            city = item.get("city") or item.get("cityName") or "Maharashtra"
            value = item.get("amount") or item.get("projectCost") or item.get("cost") or ""
            status = item.get("status") or item.get("stage") or "Unknown"
            proj_url = item.get("url") or NATIONAL_PORTAL

            return {
                "source":        "SmartCity",
                "source_url":    proj_url,
                "project_name":  proj_name,
                "builder_name":  f"{city} Smart City Mission",
                "location":      city,
                "district":      city,
                "project_value": str(value),
                "current_stage": status,
                "confidence_score": "Medium",
            }
        except Exception as exc:
            self.log.debug("SmartCity project parse error: %s", exc)
            return None
