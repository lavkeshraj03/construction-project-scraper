"""app/scrapers/base.py — Abstract base class for all scrapers."""

from __future__ import annotations

import time
from typing import Any

import requests

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("scraper.base")


class BaseScraper:
    """
    Every scraper must subclass this and implement `run()`.
    Provides:
    - Shared HTTP session with retries and rate limiting
    - run() interface contract
    - Error isolation
    """

    SOURCE_NAME: str = "Unknown"

    def __init__(self, limit: int | None = None):
        self.limit = limit or settings.MAX_PROJECTS_PER_SOURCE
        self.session = self._make_session()
        self.log = get_logger(f"scraper.{self.SOURCE_NAME.lower()}")

    def _make_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(settings.DEFAULT_HEADERS)
        return s

    def _get(self, url: str, **kwargs) -> requests.Response | None:
        """GET with retries and delay."""
        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                resp = self.session.get(
                    url,
                    timeout=settings.REQUEST_TIMEOUT,
                    **kwargs,
                )
                resp.raise_for_status()
                time.sleep(settings.REQUEST_DELAY)
                return resp
            except requests.RequestException as exc:
                self.log.warning(
                    "GET %s — attempt %d/%d failed: %s",
                    url, attempt, settings.MAX_RETRIES, exc,
                )
                if attempt < settings.MAX_RETRIES:
                    time.sleep(settings.REQUEST_DELAY * attempt)
        return None

    def _post(self, url: str, **kwargs) -> requests.Response | None:
        """POST with retries and delay."""
        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                resp = self.session.post(
                    url,
                    timeout=settings.REQUEST_TIMEOUT,
                    **kwargs,
                )
                resp.raise_for_status()
                time.sleep(settings.REQUEST_DELAY)
                return resp
            except requests.RequestException as exc:
                self.log.warning(
                    "POST %s — attempt %d/%d failed: %s",
                    url, attempt, settings.MAX_RETRIES, exc,
                )
                if attempt < settings.MAX_RETRIES:
                    time.sleep(settings.REQUEST_DELAY * attempt)
        return None

    def run(self) -> list[dict[str, Any]]:
        """
        Execute the scraper.
        Must return a list of raw record dicts.
        Must NOT raise — catch all exceptions internally.
        """
        raise NotImplementedError
