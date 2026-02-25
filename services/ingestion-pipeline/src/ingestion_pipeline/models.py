"""
SQLAlchemy ORM model for ingestion_logs — the file-level idempotency table.

This model is separate from the central src/db/models.py because it is only
used by the ingestion-pipeline Celery workers (synchronous context).
The table itself lives in the public schema, created by migration 006.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase


class IngestionBase(DeclarativeBase):
    pass


class IngestionLog(IngestionBase):
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

    def __repr__(self) -> str:
        return f"<IngestionLog {self.filename} [{self.status}]>"
