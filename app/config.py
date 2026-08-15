"""app/config.py — Centralised settings loaded from .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one level above app/)
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")


def _bool(key: str, default: bool = True) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes")


def _float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


class Settings:
    BASE_DIR: Path = _BASE_DIR

    # Paths
    DATABASE_PATH: Path = _BASE_DIR / os.getenv("DATABASE_PATH", "data/projects.db")
    OUTPUT_PATH: Path = _BASE_DIR / os.getenv("OUTPUT_PATH", "output/construction_projects.xlsx")
    LOG_PATH: Path = _BASE_DIR / os.getenv("LOG_PATH", "logs/scraper.log")
    RAW_DATA_DIR: Path = _BASE_DIR / os.getenv("RAW_DATA_DIR", "data/raw")

    # Scraping
    MAX_PROJECTS_PER_SOURCE: int = _int("MAX_PROJECTS_PER_SOURCE", 100)
    REQUEST_TIMEOUT: int = _int("REQUEST_TIMEOUT", 30)
    REQUEST_DELAY: float = _float("REQUEST_DELAY", 1.0)
    MAX_RETRIES: int = _int("MAX_RETRIES", 3)

    # AI
    AI_ENABLED: bool = _bool("AI_ENABLED", False)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "openai")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_MODEL: str = os.getenv("AI_MODEL", "gpt-4o-mini")

    # Source toggles
    ENABLE_MAHARERA: bool = _bool("ENABLE_MAHARERA", True)
    ENABLE_CPPP: bool = _bool("ENABLE_CPPP", True)
    ENABLE_GEM: bool = _bool("ENABLE_GEM", True)
    ENABLE_MAHATENDER: bool = _bool("ENABLE_MAHATENDER", True)
    ENABLE_MUNICIPAL: bool = _bool("ENABLE_MUNICIPAL", True)
    ENABLE_SMART_CITY: bool = _bool("ENABLE_SMART_CITY", True)
    ENABLE_BUILDER_WEB: bool = _bool("ENABLE_BUILDER_WEB", True)

    # Optional URL lists
    BUILDER_WEB_URLS: list[str] = [
        u.strip() for u in os.getenv("BUILDER_WEB_URLS", "").split(",") if u.strip()
    ]
    MUNICIPAL_URLS: list[str] = [
        u.strip() for u in os.getenv("MUNICIPAL_URLS", "").split(",") if u.strip()
    ]

    # HTTP headers to use for requests
    DEFAULT_HEADERS: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }


settings = Settings()
