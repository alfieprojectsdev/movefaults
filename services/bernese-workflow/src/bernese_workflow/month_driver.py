"""Run a range of days through a BPE backend, resuming at day level.

WHY THIS EXISTS
The scripts/ wrappers (run_luzon_month.sh, run_phref_year.sh, ...) skip any day
whose FIN_*.NQ0 already exists, so killing a run costs one session. The service
exposed only per-session run(), with no driver and no skip, so the cost of a
kill under the service was whatever someone re-invoked by hand (SETTLED.md §4,
"That resume is a property of scripts/, not of the system"). This is that
driver, so a multi-day run through the service can be stopped and restarted
the way the scripts' runs can.

WHAT "DONE" MEANS
A day is banked when its FIN_<year><doy><session-char>.NQ0 (or .NQ0.gz) is
non-zero, intact, and carries a companion .done marker written by this driver.
The marker is keyed to the session (FIN_<year><doy><s>.done), not to the FIN's
exact filename, so compressing or decompressing a FIN after banking does not
break the match. The marker is created only when the BPE reports success AND
the FIN file passes validation, so the first-run check and the resume check
are the same test. The FIN is re-validated on every resume, not trusted from
the marker alone: the first-run validation reads through the page cache, which
may show writes not yet on disk, so a power loss can leave a zero-byte FIN
whose marker still exists.

A BPE that fails but leaves a FIN file is not banked, because no marker is
written. A zero-byte FIN from a crash mid-write is not banked because the
re-validation catches it. A truncated .gz is detected by reading it to the end.

A day that is attempted loses its marker before the BPE starts, so a marker
always belongs to the FIN its own attempt produced. Without that, a redo that
failed after saving a FIN would be banked on the marker of the success it was
meant to replace. The marker is written only after the FIN and then the marker
itself are fsynced, so a marker on disk implies its FIN is on disk: the
re-validation below cannot catch a truncated plain .NQ0, which has no checksum.

Days banked by scripts/ (which write FIN files without .done markers) will be
rerun. This is acceptable for fresh campaigns run through the service. To adopt
a scripts/-started range, write the markers beforehand.

TO REDO A BANKED DAY, delete its .done marker (deleting the FIN works too) and
run the range again. Only the FIN is checked: RED/CRD and other products the
earlier attempt left in the campaign are not removed, so a redo that fails part
way can leave a newer FIN beside older station products.

WHEN IT STOPS
After each failed day the driver scans the BPE output for the failed step,
looks its error up in config/bernese/bpe_errors.yaml, and asks the circuit
breaker (circuit_breaker.py) whether to go on. An unknown error or a
configuration error stops the run at once; a session error stops it only after
k consecutive days fail with the same one (k = 3), or after 5 consecutive
failed days whatever their errors. The remaining days are
reported as not_run, and the failed day's outcome carries the diagnosis and
remedy. Nothing is ever deleted or retried here: a failed day is rerun by
running the range again, which skips everything already banked.

This replaced a stop after two consecutive failed days of any kind (#268).

Single-session runs only. Parallel sessions (REPR_MODE, MAXSESS) stay in the
Perl drivers for now.
"""

from __future__ import annotations

import calendar
import gzip
import logging
import os
import time
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .backends import BPEBackend
from .bpe_knowledge import DEFAULT_PATH, KnowledgeBase, load
from .circuit_breaker import (
    K_DEFAULT,
    MAX_FAILURES_DEFAULT,
    CircuitBreaker,
    Diagnosis,
    diagnose_day,
)

logger = logging.getLogger(__name__)


@dataclass
class DayOutcome:
    doy: int
    session: str
    status: str  # ok | banked | failed | not_run
    seconds: float = 0.0
    note: str = ""
    error: str = ""  # the failure's signature, as "emitter: KIND"
    explanation: str = ""  # what the knowledge base says about it, for a person


def session_for(doy: int, session_char: str = "0") -> str:
    """Bernese session name: three-digit day of year plus the session character."""
    if not 1 <= doy <= 366:
        raise ValueError(f"day of year out of range: {doy}")
    if len(session_char) != 1:
        raise ValueError(f"session character must be one character: {session_char!r}")
    return f"{doy:03d}{session_char}"


def _fin_candidates(sol_dir: Path, year: int, doy: int, session_char: str) -> tuple[Path, Path]:
    """The two names a day's FIN may have: plain, then compressed."""
    stem = f"FIN_{year}{session_for(doy, session_char)}.NQ0"
    return sol_dir / stem, sol_dir / f"{stem}.gz"


def _intact(p: Path) -> bool:
    """Exists, non-zero, and (for .gz) decompresses to the end."""
    if not p.exists() or p.stat().st_size == 0:
        return False
    if p.suffix == ".gz":
        try:
            with gzip.open(p, "rb") as f:
                while f.read(8192):
                    pass
        # zlib.error (a corrupt deflate stream) is not an OSError.
        except (EOFError, OSError, zlib.error):
            return False
    return True


def _fin_path(sol_dir: Path, year: int, doy: int, session_char: str = "0") -> Path | None:
    """Return the FIN path if it exists, is non-zero and intact, else None."""
    return next((p for p in _fin_candidates(sol_dir, year, doy, session_char) if _intact(p)), None)


def _done_marker(sol_dir: Path, year: int, doy: int, session_char: str = "0") -> Path:
    """Session-keyed marker, independent of whether the FIN is plain or compressed."""
    return sol_dir / f"FIN_{year}{session_for(doy, session_char)}.done"


def fin_banked(sol_dir: Path, year: int, doy: int, session_char: str = "0") -> bool:
    """A day is banked when its FIN is non-zero, intact, and carries a .done marker.

    The FIN is re-validated on every call, not just when the marker is written.
    This is load-bearing: the first-run validation reads through the page cache,
    which may show writes not yet on disk. A power loss between writing and
    fsync leaves a zero-byte FIN whose marker still exists. Re-checking the FIN
    here catches that; trusting the marker alone would not.
    """
    # Marker first: it is a stat, the FIN check may decompress the whole file.
    if not _done_marker(sol_dir, year, doy, session_char).exists():
        return False
    return _fin_path(sol_dir, year, doy, session_char) is not None


def _fin_mtimes(sol_dir: Path, year: int, doy: int, session_char: str) -> dict[Path, int]:
    """mtime_ns of every FIN candidate present now, to tell a fresh FIN from a stale one."""
    out: dict[Path, int] = {}
    for p in _fin_candidates(sol_dir, year, doy, session_char):
        try:
            out[p] = p.stat().st_mtime_ns
        except FileNotFoundError:
            pass
    return out


def _fresh_fin(
    sol_dir: Path, year: int, doy: int, session_char: str, before: dict[Path, int]
) -> Path | None:
    """The first intact FIN candidate this attempt wrote or changed, else None.

    Every candidate is checked, not only the one _fin_path prefers: a stale plain
    FIN left beside a fresh .gz must not make the fresh one look stale.
    """
    for p in _fin_candidates(sol_dir, year, doy, session_char):
        if _intact(p) and before.get(p) != p.stat().st_mtime_ns:
            return p
    return None


def _fsync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_marker(marker: Path, fin: Path) -> None:
    """FIN, then marker, then directory to disk, so a marker on disk implies its FIN is."""
    _fsync(fin)
    marker.touch()
    _fsync(marker)
    _fsync(marker.parent)


def run_days(
    backend: BPEBackend,
    campaign: str,
    year: int,
    doys: Iterable[int],
    *,
    sol_dir: Path,
    bpe_dir: Path,
    kb: KnowledgeBase | None = None,
    k: int = K_DEFAULT,
    max_failures: int = MAX_FAILURES_DEFAULT,
    session_char: str = "0",
) -> list[DayOutcome]:
    """Run each day in ascending order, skipping banked days. See module docstring.

    ``bpe_dir`` is the campaign's BPE/ directory, where a failed step's output
    is found. ``kb`` defaults to config/bernese/bpe_errors.yaml, loaded before
    the first day so that a broken file stops the run before Bernese starts.
    """
    days = sorted(set(doys))
    last = 366 if calendar.isleap(year) else 365
    if days and days[-1] > last:
        raise ValueError(f"day of year {days[-1]} does not exist in {year}")
    if not bpe_dir.is_dir():
        # A wrong path would make every failure "no failed BPE step" and stop
        # the run with a misleading diagnosis; say so before Bernese starts.
        raise ValueError(f"BPE directory does not exist: {bpe_dir}")
    if not sol_dir.is_dir():
        # Same reasoning: every FIN would look missing, so the first day would be
        # run in full and then reported as "no valid FIN", and the run stopped.
        raise ValueError(f"SOL directory does not exist: {sol_dir}")
    if kb is None:
        kb = load(DEFAULT_PATH)
    breaker = CircuitBreaker(k, max_failures)
    out: list[DayOutcome] = []
    for i, doy in enumerate(days):
        session = session_for(doy, session_char)
        if fin_banked(sol_dir, year, doy, session_char):
            logger.info("DOY %03d banked, skipping", doy)
            out.append(DayOutcome(doy, session, "banked"))
            continue

        # This attempt replaces whatever the marker vouched for (see module docstring).
        _done_marker(sol_dir, year, doy, session_char).unlink(missing_ok=True)
        before = _fin_mtimes(sol_dir, year, doy, session_char)
        started = time.time()
        t0 = time.monotonic()
        try:
            result = backend.run(campaign, year, session)
            error = None
        except Exception as exc:  # noqa: BLE001 -- a day's error is that day's failure
            # The real backend raises on timeout and on RINEX header validation.
            # The day is recorded and the report still returned, and the run
            # stops as unknown whatever BPE/ shows (see the halt below).
            # KeyboardInterrupt is not an Exception and propagates.
            result = None
            error = f"{type(exc).__name__}: {exc}"
        seconds = time.monotonic() - t0
        # A FIN left by an earlier failed attempt is not this run's output. mtime
        # granularity (ms) is far below a BPE day (minutes), so equality means untouched.
        fin = _fresh_fin(sol_dir, year, doy, session_char, before)
        stale = fin is None and _fin_path(sol_dir, year, doy, session_char) is not None
        if result is not None and result.success and fin is not None:
            _write_marker(_done_marker(sol_dir, year, doy, session_char), fin)
            out.append(DayOutcome(doy, session, "ok", seconds))
            breaker.success()
            logger.info("DOY %03d ok in %.0f s", doy, seconds)
            continue

        if result is None:
            note = f"backend raised {error}"
        elif not result.success:
            note = "BPE reported failure"
        elif stale:
            note = "BPE reported success but the FIN file predates this run"
        else:
            note = "BPE reported success but no valid FIN file"
        try:
            diagnosis = diagnose_day(bpe_dir, year, session, started, kb)
        except OSError as exc:
            # Reading BPE/ must not cost the report: diagnose as unknown, which halts.
            logger.error("DOY %03d: could not read %s: %s", doy, bpe_dir, exc)
            diagnosis = Diagnosis(None, None, None, unreadable=f"{type(exc).__name__}: {exc}")
        explanation = diagnosis.explanation(kb)
        out.append(DayOutcome(doy, session, "failed", seconds, note, diagnosis.label, explanation))
        logger.warning("DOY %03d failed: %s; %s", doy, note, diagnosis.label)
        halt = breaker.failure(diagnosis)
        if halt is None and result is None:
            # A backend that raised (timeout, refused pre-flight) is unknown even
            # when a step left a known session error: that error does not explain
            # the raise, and another day would cost another timeout.
            halt = f"unknown failure (backend raised {error}); no remedy on file"
        if halt is not None:
            logger.error("stopping: %s\n%s", halt, explanation)
            out.extend(
                DayOutcome(d, session_for(d, session_char), "not_run", note=f"stopped: {halt}")
                for d in days[i + 1 :]
            )
            break
    return out
