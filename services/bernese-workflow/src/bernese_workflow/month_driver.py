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
A day is banked when FIN_<year><doy><session-char>.NQ0 (or .NQ0.gz) exists in
the results directory: the same evidence the wrappers use. A BPE that reports
success but leaves no FIN file counts as failed, because a later resume could
not tell it had run.

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

import logging
import time
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
    return f"{doy:03d}{session_char}"


def fin_banked(sol_dir: Path, year: int, doy: int, session_char: str = "0") -> bool:
    stem = f"FIN_{year}{session_for(doy, session_char)}.NQ0"
    return (sol_dir / stem).exists() or (sol_dir / f"{stem}.gz").exists()


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
    out: list[DayOutcome] = []
    consecutive = 0
    for i, doy in enumerate(days):
        session = session_for(doy, session_char)
        if fin_banked(sol_dir, year, doy, session_char):
            logger.info("DOY %03d banked, skipping", doy)
            out.append(DayOutcome(doy, session, "banked"))
            continue

        t0 = time.monotonic()
        result = backend.run(campaign, year, session)  # a kill propagates; resume reruns it
        seconds = time.monotonic() - t0
        if result.success and fin_banked(sol_dir, year, doy, session_char):
            out.append(DayOutcome(doy, session, "ok", seconds))
            consecutive = 0
            logger.info("DOY %03d ok in %.0f s", doy, seconds)
            continue

        note = (
            "BPE reported failure" if not result.success else "BPE reported success but no FIN file"
        )
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
