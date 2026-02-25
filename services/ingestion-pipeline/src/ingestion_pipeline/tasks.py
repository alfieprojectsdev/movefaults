"""
Celery tasks for the RINEX ingestion pipeline.

Pipeline order (via Celery chain in pipeline.py):
  standardize_format → validate_rinex → load_to_postgres

Each task that feeds into the next returns the output file path so that
Celery's chain mechanism can pass it as the first positional argument.

teqc integration:
  teqc is the primary QC backend (gfzrnx not yet acquired).
  If teqc is not in PATH, validate_rinex logs a warning and continues —
  the raw header check is still enforced.
"""

import gzip
import logging
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .celery import app
from .database import SessionLocal
from .models import IngestionLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RINEX header parser
# ---------------------------------------------------------------------------

def _parse_rinex_header(file_path: str) -> dict:
    """
    Extract metadata from a RINEX 2.x or 3.x observation file header.

    RINEX header records are fixed-width 80-char lines:
      columns  1–60: value field
      columns 61–80: label (right-justified, space-padded)

    Returns a dict with keys present in the header; missing fields are absent.
    """
    meta: dict = {}
    try:
        with open(file_path, encoding="ascii", errors="replace") as f:
            for raw_line in f:
                line = raw_line.rstrip("\n")
                if len(line) < 61:
                    if "END OF HEADER" in line:
                        break
                    continue
                label = line[60:].strip()
                value = line[:60].strip()

                if label == "MARKER NAME":
                    # First token is the 4-char station code
                    parts = value.split()
                    if parts:
                        meta["station_code"] = parts[0][:10]

                elif label == "INTERVAL":
                    try:
                        meta["sampling_interval"] = float(value)
                    except ValueError:
                        pass

                elif label == "REC # / TYPE / VERS":
                    # cols 21–40 (0-indexed 20–39): receiver type
                    meta["receiver_type"] = raw_line[20:40].strip()

                elif label == "ANT # / TYPE":
                    # cols 21–40 (0-indexed 20–39): antenna type
                    meta["antenna_type"] = raw_line[20:40].strip()

                elif label == "TIME OF FIRST OBS":
                    meta["start_time_raw"] = value

                elif label == "TIME OF LAST OBS":
                    meta["end_time_raw"] = value

                elif label == "END OF HEADER":
                    break
    except OSError as e:
        logger.warning("Could not read RINEX header from %s: %s", file_path, e)
    return meta


def _parse_rinex_time(raw: str) -> datetime | None:
    """Parse a RINEX TIME OF FIRST/LAST OBS field into a UTC datetime."""
    # Format: YYYY   MM   DD   HH   MM  SS.SSSSSSS     TIME SYSTEM
    parts = raw.split()
    if len(parts) < 6:
        return None
    try:
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        hour, minute = int(parts[3]), int(parts[4])
        sec_f = float(parts[5])
        second = int(sec_f)
        microsecond = int((sec_f - second) * 1_000_000)
        return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Task logic — plain functions (independently testable without Celery)
# ---------------------------------------------------------------------------

def _standardize_format(file_path: str) -> str:
    """
    Decompress and convert the input file to a plain RINEX observation file.

    Handles:
      .gz   — gzip (Python stdlib)
      .zip  — zip archive (Python stdlib), extracts first member
      .Z    — Unix compress (requires gunzip in PATH)
      .crx / .??d — Hatanaka compression (requires crx2rnx in PATH)

    Returns the path to the standardized file (in a temp directory).
    The caller is responsible for cleanup; in production the Celery worker
    temp dir is cleaned by the OS on worker restart.
    """
    logger.info("standardize_format: %s", file_path)
    path = Path(file_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="pogf_ingest_"))
    out_path = temp_dir / path.name

    # ── Decompression ─────────────────────────────────────────────────────
    suffix = path.suffix.lower()

    if suffix == ".gz":
        out_path = temp_dir / path.stem
        with gzip.open(path, "rb") as f_in, open(out_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    elif suffix == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            first_member = zf.namelist()[0]
            zf.extract(first_member, temp_dir)
            out_path = temp_dir / first_member

    elif path.suffix == ".Z":
        # Unix compress — requires system gunzip
        out_path = temp_dir / path.stem
        try:
            with open(out_path, "wb") as f_out:
                subprocess.run(["gunzip", "-c", str(path)], stdout=f_out, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(f"gunzip failed for {file_path}: {e}") from e

    else:
        # Not compressed — copy to temp for uniform downstream handling
        shutil.copy(path, out_path)

    # ── Hatanaka decompression ─────────────────────────────────────────────
    # .crx (RINEX 3.x Hatanaka) or .??d (RINEX 2.x Hatanaka)
    out_suffix = out_path.suffix.lower()
    is_hatanaka = out_suffix == ".crx" or (
        len(out_suffix) == 3 and out_suffix[1:2].isdigit() and out_suffix[2] == "d"
    )

    if is_hatanaka:
        rnx_path = out_path.with_suffix(
            ".rnx" if out_suffix == ".crx" else out_suffix[:-1] + "o"
        )
        try:
            subprocess.run(["crx2rnx", str(out_path)], check=True, capture_output=True)
            out_path = rnx_path
            logger.info("Hatanaka decompressed: %s → %s", out_path.name, rnx_path.name)
        except FileNotFoundError:
            logger.warning("crx2rnx not in PATH — passing Hatanaka file as-is")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"crx2rnx failed for {out_path}: {e}") from e

    logger.info("standardize_format done: %s", out_path)
    return str(out_path)


def _validate_rinex(file_path: str) -> str:
    """
    Validate that file_path is a well-formed RINEX observation file.

    Two-stage validation:
      1. Header scan — reads first 10 lines looking for 'RINEX VERSION' or
         'CRINEX VERS'. Fast, no external dependencies.
      2. teqc QC — runs 'teqc +qc <file>' for deeper quality check.
         If teqc is not in PATH, logs a warning and skips (non-fatal).

    Returns file_path unchanged so the Celery chain can pass it onward.
    Raises ValueError on invalid header (marks Celery task as FAILED).
    """
    logger.info("validate_rinex: %s", file_path)
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # ── Stage 1: header scan ──────────────────────────────────────────────
    is_rinex = False
    try:
        with open(path, "rb") as f:
            for _ in range(10):
                line = f.readline().decode("utf-8", errors="ignore")
                if "RINEX VERSION" in line or "CRINEX VERS" in line:
                    is_rinex = True
                    break
    except OSError as e:
        raise ValueError(f"Cannot read {file_path}: {e}") from e

    if not is_rinex:
        raise ValueError(f"No RINEX VERSION marker found in first 10 lines of {file_path}")

    # ── Stage 2: teqc QC (optional) ───────────────────────────────────────
    try:
        result = subprocess.run(
            ["teqc", "+qc", str(path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            logger.warning("teqc QC warnings for %s:\n%s", file_path, result.stderr[:500])
        else:
            logger.info("teqc QC passed: %s", file_path)
    except FileNotFoundError:
        logger.warning("teqc not in PATH — skipping QC for %s", file_path)
    except subprocess.TimeoutExpired:
        logger.warning("teqc timed out for %s — skipping QC", file_path)

    return file_path


def _load_to_postgres(file_path: str, file_hash: str) -> str:
    """
    Write a RinexFile row to public.rinex_files and mark IngestionLog success.

    Parses the RINEX header to extract:
      station_code, sampling_interval, start_time, end_time,
      receiver_type, antenna_type.

    Looks up the station by station_code in public.stations. If the station
    is not found, raises ValueError (Celery marks task FAILED and the
    IngestionLog row is updated to status='failed').
    """
    from src.db.models import RinexFile, Station  # central ORM (public schema)

    logger.info("load_to_postgres: %s", file_path)
    meta = _parse_rinex_header(file_path)

    station_code = meta.get("station_code")
    start_time = _parse_rinex_time(meta.get("start_time_raw", ""))
    end_time = _parse_rinex_time(meta.get("end_time_raw", ""))

    session = SessionLocal()
    try:
        # ── Resolve station FK ────────────────────────────────────────────
        station = None
        if station_code:
            station = session.query(Station).filter_by(station_code=station_code).first()

        if station is None:
            raise ValueError(
                f"Station '{station_code}' from RINEX header not found in public.stations. "
                "Register the station first or correct the MARKER NAME field."
            )

        # ── Compute MD5 for dedup (reuse SHA256 from scanner as proxy) ────
        import hashlib
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        md5 = h.hexdigest()

        # ── Insert RinexFile (skip if already catalogued) ─────────────────
        existing_rnx = session.query(RinexFile).filter_by(hash_md5=md5).first()
        if existing_rnx is None:
            rnx = RinexFile(
                station_id=station.id,
                filepath=file_path,
                start_time=start_time or datetime.now(timezone.utc),
                end_time=end_time or datetime.now(timezone.utc),
                sampling_interval=meta.get("sampling_interval"),
                receiver_type=meta.get("receiver_type"),
                antenna_type=meta.get("antenna_type"),
                hash_md5=md5,
            )
            session.add(rnx)

        # ── Update IngestionLog ────────────────────────────────────────────
        log = session.get(IngestionLog, file_hash)
        if log:
            log.status = "success"
            log.station_code = station_code
            log.ingested_at = datetime.now(timezone.utc)

        session.commit()
        logger.info("Ingested %s → station %s", file_path, station_code)
        return f"success:{file_path}"

    except Exception as exc:
        session.rollback()
        log = session.get(IngestionLog, file_hash)
        if log:
            log.status = "failed"
            log.error_message = str(exc)
            session.commit()
        raise

    finally:
        session.close()


# ---------------------------------------------------------------------------
# Celery task wrappers — thin shells that call the plain functions above.
# Keeping business logic in plain functions makes them independently testable
# without needing a Celery worker or mocked broker.
# ---------------------------------------------------------------------------

@app.task(name="ingestion_pipeline.tasks.standardize_format")
def standardize_format(file_path: str) -> str:
    return _standardize_format(file_path)


@app.task(name="ingestion_pipeline.tasks.validate_rinex")
def validate_rinex(file_path: str) -> str:
    return _validate_rinex(file_path)


@app.task(name="ingestion_pipeline.tasks.load_to_postgres")
def load_to_postgres(file_path: str, file_hash: str) -> str:
    return _load_to_postgres(file_path, file_hash)
