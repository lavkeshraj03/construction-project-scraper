"""app/database.py — SQLite persistence layer via SQLAlchemy core."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("database")


class Base(DeclarativeBase):
    pass


class ProjectRecord(Base):
    """Single table that holds every collected project."""

    __tablename__ = "projects"

    # ── Primary key ──────────────────────────────────────────────────────────
    id          = Column(Integer, primary_key=True, autoincrement=True)
    project_id  = Column(String(64), unique=True, nullable=False, index=True)

    # ── Source tracking ───────────────────────────────────────────────────────
    source      = Column(String(64), nullable=False)
    source_url  = Column(Text)
    rera_number = Column(String(64), index=True)
    tender_number = Column(String(128), index=True)

    # ── Project information ───────────────────────────────────────────────────
    builder_name    = Column(Text)
    project_name    = Column(Text)
    location        = Column(Text)
    district        = Column(String(64))
    pincode         = Column(String(10))
    project_value   = Column(Text)
    project_type    = Column(String(64))

    # ── Contact information ───────────────────────────────────────────────────
    decision_maker  = Column(Text)
    mobile          = Column(Text)
    email           = Column(Text)
    architect       = Column(Text)
    contractor      = Column(Text)
    builder_architect_contractor = Column(Text)

    # ── Construction stage ────────────────────────────────────────────────────
    current_stage          = Column(String(64))
    completion_percentage  = Column(Float)
    expected_completion_date = Column(String(32))

    # ── Lead intelligence ─────────────────────────────────────────────────────
    lead_score          = Column(Integer)
    expected_order_value = Column(Text)
    competition         = Column(Text)

    # ── Material ──────────────────────────────────────────────────────────────
    material_required    = Column(String(16))   # Yes / No / Unknown
    material_categories  = Column(Text)         # Granite, Marble, …

    # ── Quality ───────────────────────────────────────────────────────────────
    confidence_score = Column(String(16))       # High / Medium / Low

    # ── Deduplication ─────────────────────────────────────────────────────────
    duplicate_status = Column(String(16), default="unique")   # unique / duplicate
    duplicate_of     = Column(String(64))

    # ── Raw data ──────────────────────────────────────────────────────────────
    raw_data = Column(Text)   # JSON blob of raw extracted fields

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class ScrapeRunRecord(Base):
    """Tracks each scraper execution for the Scrape Log sheet."""

    __tablename__ = "scrape_runs"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    run_id       = Column(String(64), nullable=False)
    source       = Column(String(64), nullable=False)
    start_time   = Column(DateTime)
    end_time     = Column(DateTime)
    records_found  = Column(Integer, default=0)
    records_added  = Column(Integer, default=0)
    duplicates     = Column(Integer, default=0)
    errors         = Column(Integer, default=0)
    status         = Column(String(16))   # SUCCESS / PARTIAL / ERROR / SKIPPED


# ─── Engine / Session ──────────────────────────────────────────────────────────

def _make_engine():
    db_path: Path = settings.DATABASE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    # Enable WAL for concurrent read safety
    @event.listens_for(engine, "connect")
    def set_wal(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create all tables and indexes."""
    Base.metadata.create_all(bind=engine)
    log.info("Database initialised at %s", settings.DATABASE_PATH)


def get_session() -> Session:
    return SessionLocal()


# ─── CRUD helpers ──────────────────────────────────────────────────────────────

def upsert_project(session: Session, record: dict[str, Any]) -> tuple[bool, str]:
    """
    Insert or update a project record.
    Returns (is_new: bool, project_id: str).
    """
    pid = record["project_id"]
    existing = session.query(ProjectRecord).filter_by(project_id=pid).first()
    now = datetime.now(timezone.utc)
    if existing:
        for k, v in record.items():
            if k not in ("id", "created_at"):
                setattr(existing, k, v)
        existing.updated_at = now
        session.commit()
        return False, pid
    else:
        obj = ProjectRecord(**record, created_at=now, updated_at=now)
        session.add(obj)
        session.commit()
        return True, pid


def all_projects(session: Session) -> list[ProjectRecord]:
    return session.query(ProjectRecord).order_by(ProjectRecord.created_at).all()


def log_scrape_run(session: Session, run: dict[str, Any]) -> None:
    obj = ScrapeRunRecord(**run)
    session.add(obj)
    session.commit()


def all_scrape_runs(session: Session) -> list[ScrapeRunRecord]:
    return session.query(ScrapeRunRecord).order_by(ScrapeRunRecord.start_time).all()
