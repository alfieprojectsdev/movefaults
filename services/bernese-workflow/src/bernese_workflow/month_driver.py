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

Days banked by scripts/ (which write FIN files without .done markers) will be
rerun. This is acceptable for fresh campaigns run through the service. To adopt
a scripts/-started range, write the markers beforehand.

WHEN IT STOPS
Two consecutive failed days stop the run; the remaining days are reported as
not_run. That is the weekend plan's stop condition ("a BPE fails twice"), made
mechanical. An isolated failure is reported and the run continues. Nothing is
ever deleted or retried here: a failed day is rerun by running the range again,
which skips everything already banked.

Single-session runs only. Parallel sessions (REPR_MODE, MAXSESS) stay in the
Perl drivers for now.
"""

from __future__ import annotations

import calendar
import gzip
import logging
import time
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .backends import BPEBackend

logger = logging.getLogger(__name__)

STOP_AFTER_CONSECUTIVE_FAILURES = 2


@dataclass
class DayOutcome:
    doy: int
    session: str
    status: str  # ok | banked | failed | not_run
    seconds: float = 0.0
    note: str = ""


def session_for(doy: int, session_char: str = "0") -> str:
    """Bernese session name: three-digit day of year plus the session character."""
    if not 1 <= doy <= 366:
        raise ValueError(f"day of year out of range: {doy}")
    if len(session_char) != 1:
        raise ValueError(f"session character must be one character: {session_char!r}")
    return f"{doy:03d}{session_char}"


def _fin_path(sol_dir: Path, year: int, doy: int, session_char: str = "0") -> Path | None:
    """Return the FIN path if it exists, is non-zero and intact, else None."""
    stem = f"FIN_{year}{session_for(doy, session_char)}.NQ0"
    for name in (stem, f"{stem}.gz"):
        p = sol_dir / name
        if not p.exists() or p.stat().st_size == 0:
            continue
        if name.endswith(".gz"):
            try:
                with gzip.open(p, "rb") as f:
                    while f.read(8192):
                        pass
            # zlib.error (a corrupt deflate stream) is not an OSError.
            except (EOFError, OSError, zlib.error):
                continue
        return p
    return None


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
    stem = f"FIN_{year}{session_for(doy, session_char)}.NQ0"
    out: dict[Path, int] = {}
    for name in (stem, f"{stem}.gz"):
        p = sol_dir / name
        try:
            out[p] = p.stat().st_mtime_ns
        except FileNotFoundError:
            pass
    return out


def run_days(
    backend: BPEBackend,
    campaign: str,
    year: int,
    doys: Iterable[int],
    *,
    sol_dir: Path,
    session_char: str = "0",
) -> list[DayOutcome]:
    """Run each day in ascending order, skipping banked days. See module docstring."""
    days = sorted(set(doys))
    last = 366 if calendar.isleap(year) else 365
    if days and days[-1] > last:
        raise ValueError(f"day of year {days[-1]} does not exist in {year}")
    out: list[DayOutcome] = []
    consecutive = 0
    for i, doy in enumerate(days):
        session = session_for(doy, session_char)
        if fin_banked(sol_dir, year, doy, session_char):
            logger.info("DOY %03d banked, skipping", doy)
            out.append(DayOutcome(doy, session, "banked"))
            continue

        before = _fin_mtimes(sol_dir, year, doy, session_char)
        t0 = time.monotonic()
        try:
            result = backend.run(campaign, year, session)
            error = None
        except Exception as exc:  # noqa: BLE001 -- a day's error is that day's failure
            # The real backend raises on timeout and on RINEX header validation.
            # Those are per-day failures, not reasons to abandon the range and
            # its report. KeyboardInterrupt is not an Exception and still stops.
            result = None
            error = f"{type(exc).__name__}: {exc}"
        seconds = time.monotonic() - t0
        fin = _fin_path(sol_dir, year, doy, session_char)
        # A FIN left by an earlier failed attempt is not this run's output. mtime
        # granularity (ms) is far below a BPE day (minutes), so equality means untouched.
        stale = fin is not None and before.get(fin) == fin.stat().st_mtime_ns
        if result is not None and result.success and fin is not None and not stale:
            _done_marker(sol_dir, year, doy, session_char).touch()
            out.append(DayOutcome(doy, session, "ok", seconds))
            consecutive = 0
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
        out.append(DayOutcome(doy, session, "failed", seconds, note))
        consecutive += 1
        logger.warning("DOY %03d failed: %s", doy, note)
        if consecutive >= STOP_AFTER_CONSECUTIVE_FAILURES:
            logger.error("stopping: %d consecutive failures", consecutive)
            out.extend(
                DayOutcome(d, session_for(d, session_char), "not_run") for d in days[i + 1 :]
            )
            break
    return out
