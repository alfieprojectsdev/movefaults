from .celery import app
from .core.idempotency import calculate_file_hash, create_or_update_job, get_job_status, update_job_status
from .models import IngestionStatus
from .filters.validator import validate_rinex_file
from .filters.standardizer import standardize_rinex_file
from .filters.loader import load_rinex_file
from celery import chain
import logging
import os

logger = logging.getLogger(__name__)

@app.task
def start_ingestion(file_path: str):
    """Entry point for ingestion pipeline."""
    logger.info(f"Starting ingestion for: {file_path}")
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return "FILE_NOT_FOUND"

    # 1. Calculate Hash
    try:
        file_hash = calculate_file_hash(file_path)
    except Exception as e:
        logger.error(f"Failed to calculate hash: {e}")
        return "HASH_FAILED"

    # 2. Check/Create Job
    # If job exists and completed, stop.
    try:
        status = get_job_status(file_hash)
        if status == IngestionStatus.COMPLETED:
            logger.info(f"File {file_path} already ingested. Hash: {file_hash}")
            # Optionally remove the duplicate file
            # os.remove(file_path)
            return "DUPLICATE"

        create_or_update_job(file_hash, os.path.basename(file_path))
    except Exception as e:
        logger.error(f"Database error during job creation: {e}")
        # Fail gracefully?
        return "DB_ERROR"

    # 3. Chain
    # validate -> standardize -> load
    chain(
        validate_task.s(file_path, file_hash),
        standardize_task.s(file_hash),
        load_task.s(file_hash)
    ).apply_async()

    return "STARTED"

@app.task
def validate_task(file_path: str, file_hash: str):
    """Step 1: Validate"""
    logger.info(f"Validating {file_path}")
    update_job_status(file_hash, IngestionStatus.PROCESSING)
    
    is_valid, error = validate_rinex_file(file_path)

    if not is_valid:
        logger.error(f"Validation failed for {file_path}: {error}")
        update_job_status(file_hash, IngestionStatus.INVALID, error)
        # Move to quarantine? For now just stop.
        raise Exception(f"Validation failed: {error}")

    return file_path

@app.task
def standardize_task(file_path: str, file_hash: str):
    """Step 2: Standardize"""
    logger.info(f"Standardizing {file_path}")
    try:
        std_path = standardize_rinex_file(file_path)
        return std_path
    except Exception as e:
        logger.error(f"Standardization failed: {e}")
        update_job_status(file_hash, IngestionStatus.FAILED, str(e))
        raise e

@app.task
def load_task(file_path: str, file_hash: str):
    """Step 3: Load"""
    logger.info(f"Loading {file_path}")
    try:
        final_path = load_rinex_file(file_path, file_hash)
        update_job_status(file_hash, IngestionStatus.COMPLETED)
        logger.info(f"Ingestion complete: {final_path}")
        return final_path
    except Exception as e:
        logger.error(f"Loading failed: {e}")
        update_job_status(file_hash, IngestionStatus.FAILED, str(e))
        raise e

# Legacy wrappers
@app.task
def validate_rinex(file_path: str):
    """Legacy stub wrapper"""
    return validate_rinex_file(file_path)

@app.task
def ingest_rinex(file_path: str):
    """Legacy wrapper"""
    start_ingestion.delay(file_path)
