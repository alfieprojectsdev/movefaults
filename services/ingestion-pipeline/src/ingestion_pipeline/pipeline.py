"""
Celery chain orchestration for the RINEX ingestion pipeline.

The ingestion pipeline runs three tasks in sequence:
  1. standardize_format — decompress and convert to plain RINEX 3.x
  2. validate_rinex     — check RINEX header + run teqc QC (stubbed)
  3. load_to_postgres   — write RinexFile row + update IngestionLog

Each task receives the output path of the previous task as its first argument
(Celery's signature chaining via .s()). file_hash is passed as a keyword
argument to load_to_postgres so it survives the chain.
"""

from celery import chain

from .tasks import load_to_postgres, standardize_format, validate_rinex


def trigger_ingest(file_path: str, file_hash: str) -> str:
    """
    Build and dispatch the ingestion chain for a single file.
    Returns the Celery task result ID.
    """
    ingest_chain = chain(
        standardize_format.s(file_path),
        validate_rinex.s(),
        load_to_postgres.s(file_hash=file_hash),
    )
    result = ingest_chain.apply_async()
    return result.id
