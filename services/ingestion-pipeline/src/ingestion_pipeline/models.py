"""
SQLAlchemy ORM model for ingestion_logs — the file-level idempotency table.

Uses the central Base from src.db.models so that ingestion_logs participates
in the same SQLAlchemy metadata as the rest of the public schema. The table
is created by migration 006 in the root Alembic history.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from src.db.models import Base


class IngestionLog(Base):
    """
    One row per unique RINEX file, keyed by SHA-256 hash.

    The hash is the idempotency key: the same file submitted twice (from
    different paths or after a rename) will match the existing row and be
    skipped if status == 'success'.

    status lifecycle: pending → processing → success | failed
    """

    __tablename__ = "ingestion_logs"

    file_hash = Column(String(64), primary_key=True)
    filename = Column(String(1024), nullable=False)
    filepath = Column(Text, nullable=False)
    station_code = Column(String(10))           # loose ref to public.stations
    status = Column(String(20), nullable=False, default="pending")
    queued_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    ingested_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    qc_obs_count    = Column(Integer)
    qc_cycle_slips  = Column(Integer)
    qc_mp1_rms      = Column(Float)
    qc_mp2_rms      = Column(Float)

    def __repr__(self) -> str:
        return f"<IngestionLog {self.filename} [{self.status}]>"
