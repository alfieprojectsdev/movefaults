import hashlib
import logging
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..models import IngestionJob, IngestionStatus, Base
import os

logger = logging.getLogger(__name__)

# Assuming connection string in env or default
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "pogf_db")

DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    # Ensure tables exist (simple migration for now)
    Base.metadata.create_all(engine)
except Exception as e:
    logger.warning(f"Could not connect to database or create tables: {e}")
    # Fallback or allow failure later when tasks run

def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate hash for {file_path}: {e}")
        raise

def get_job_status(file_hash: str) -> Optional[IngestionStatus]:
    """Check if file has been processed."""
    session = Session()
    try:
        job = session.query(IngestionJob).filter_by(file_hash=file_hash).first()
        if job:
            return job.status
        return None
    finally:
        session.close()

def create_or_update_job(file_hash: str, filename: str) -> str:
    """
    Create a new ingestion job or update existing one if retryable.
    Returns the file_hash (which acts as the job key).
    """
    session = Session()
    try:
        job = session.query(IngestionJob).filter_by(file_hash=file_hash).first()
        if not job:
            job = IngestionJob(
                file_hash=file_hash,
                original_filename=filename,
                status=IngestionStatus.PENDING
            )
            session.add(job)
        elif job.status in [IngestionStatus.FAILED, IngestionStatus.INVALID]:
            # Retry
            job.status = IngestionStatus.PENDING
            job.error_message = None
            # job.updated_at is handled by onupdate

        session.commit()
        return job.file_hash
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def update_job_status(file_hash: str, status: IngestionStatus, error_message: Optional[str] = None):
    session = Session()
    try:
        job = session.query(IngestionJob).filter_by(file_hash=file_hash).first()
        if job:
            job.status = status
            if error_message:
                job.error_message = error_message
            session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
