"""Find solved days whose network came apart: the run says ok, the coordinates don't.

WHY THIS EXISTS
A Bernese day can finish cleanly and still be wrong. In PHSUP 2023, six of 365 days
ended with part of the network shifted against the rest, by about 20 mm on DOY 254
and about 195 mm on DOY 271. Every one was recorded as ok. On the clearest days the
shifted stations hang off the others by a single baseline. The datum check then
rejects the reference stations on the far side, so a low datum count often follows,
but it doesn't identify these days: DOY 087 kept 8 datum stations and is bad, while
DOY 285 kept 4 and is fine.

WHAT IT MEASURES
Each station's horizontal position on a day, against the median of its own positions
over the 14 days before and, separately, the 14 days after. The smaller of the two
differences counts. A real offset, such as an earthquake, agrees with one side or
the other, so it isn't reported; a day that is simply wrong agrees with neither.

That needs both sides. Near the start or end of the data only one side has enough
days, and a real offset there looks the same as a bad day, so such a day is still
reported but is marked as compared on one side only.

A day is suspect when at least 25% of its stations moved more than 15 mm. In PHSUP
2023 the median day has 1% of stations past 15 mm and the 95th percentile is 8%. The
six suspect days have 26% to 97%, and the highest of the other 359 days has 18%.

WHAT IT DOESN'T DO
It reads only saved results and changes nothing. It doesn't say why a day went wrong
or repair it. The groups and links it prints describe the split: they come from the
largest gap in the shifts, on whichever of east or north has the wider one, and a
day can be suspect without a clean split. A day it can't compare (too few stations
with enough neighbouring days) is counted as not checked, never as clean.

Usage:
    bernese-check-network --campaign PHSUP --year 2023
    bernese-check-network --campaign PHSUP --year 2023 --from 240 --to 270

Exit codes: 0 no suspect day, 1 at least one suspect day, 2 nothing could be checked.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import statistics
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["DayFinding", "NetworkCheck", "check_year", "main", "read_crd", "read_prc"]

MOVED_MM = 15.0  # horizontal shift that counts a station as moved
SUSPECT_SHARE = 0.25  # share of moved stations that makes a day suspect
WINDOW_DAYS = 14  # days compared on each side
MIN_REFERENCE_DAYS = 5  # a side with fewer days than this is not used
MIN_STATIONS = 20  # a day with fewer comparable stations is not checked
MIN_GROUP = 8  # the smallest group a split may have, on a network large enough for it

XYZ = tuple[float, float, float]

_CRD_LINE = re.compile(
    r"^\s*\d+\s+(\S{4})\b.*?\s(-?\d+\.\d{3,5})\s+(-?\d+\.\d{3,5})\s+(-?\d+\.\d{3,5})\s+([A-Z])\b"
)
_BASELINE_LINE = re.compile(r"^\s*\d+\s+(\S{4}) \S+\s+(\S{4}) \S+\s+tot\s")
_DATUM_LINE = re.compile(r"^\s*\|\s*\d+ \| (\S{4}) \S*\s*\| \S W \|")
_FIDUCIAL_SECTION = "Verification of fiducial stations"


@dataclass(frozen=True)
class DayFinding:
    """One suspect day. ``str()`` is the line a report prints."""

    doy: int
    stations: int  # stations compared
    moved: int  # of those, how many moved more than MOVED_MM
    datum: tuple[str, ...] = ()  # reference stations the datum check kept
    groups: tuple[int, int] | None = None  # sizes of the two groups, if split
    separation_mm: float | None = None  # distance between the groups' medians
    links: tuple[tuple[str, str], ...] = ()  # baselines joining the two groups
    one_sided: bool = False  # most moved stations had enough days on one side only

    @property
    def share(self) -> float:
        return self.moved / self.stations

    def __str__(self) -> str:
        text = (
            f"DOY {self.doy:03d}: {self.moved} of {self.stations} stations moved more "
            f"than {MOVED_MM:.0f} mm"
        )
        if self.datum:  # empty means the processing summary didn't say, not that none were kept
            text += f"; {len(self.datum)} datum stations"
        if self.groups is not None and self.separation_mm is not None:
            text += (
                f"; groups of {self.groups[0]} and {self.groups[1]} stations "
                f"{self.separation_mm:.0f} mm apart"
            )
            if self.links:
                joined = ", ".join(f"{a}-{b}" for a, b in self.links[:3])
                more = f" and {len(self.links) - 3} more" if len(self.links) > 3 else ""
                text += f", joined by {joined}{more}"
        if self.one_sided:
            text += "; compared on one side only, so a real offset isn't ruled out"
        return text


def _days(n: int) -> str:
    return f"{n} day{'' if n == 1 else 's'}"


@dataclass
class NetworkCheck:
    """What a check looked at, so that nothing unchecked reads as clean."""

    checked: list[int] = field(default_factory=list)
    not_checked: list[int] = field(default_factory=list)
    findings: list[DayFinding] = field(default_factory=list)

    def summary(self) -> str:
        """One line for a run's result."""
        if not self.checked:
            return f"network check: none of {_days(len(self.not_checked))} could be checked"
        if self.findings:
            days = ", ".join(f"{f.doy:03d}" for f in self.findings)
            text = (
                f"network check: {len(self.findings)} of {_days(len(self.checked))} "
                f"suspect (DOY {days})"
            )
            one_sided = ", ".join(f"{f.doy:03d}" for f in self.findings if f.one_sided)
            if one_sided:
                text += (
                    f"; DOY {one_sided} compared on one side only, a real offset isn't ruled out"
                )
        else:
            text = f"network check: {_days(len(self.checked))} checked, none suspect"
        if self.not_checked:
            text += f"; {_days(len(self.not_checked))} not checked"
        return text


def read_crd(path: Path) -> dict[str, XYZ]:
    """The stations a solution estimated: a line with no flag was only carried along."""
    out: dict[str, XYZ] = {}
    with path.open(errors="replace") as fh:
        for line in fh:
            m = _CRD_LINE.match(line)
            if m:
                out[m[1]] = (float(m[2]), float(m[3]), float(m[4]))
    return out


def read_prc(path: Path) -> tuple[tuple[str, ...], list[tuple[str, str]]]:
    """The datum stations and baselines of a day, from its processing summary."""
    text = path.read_text(errors="replace")
    baselines = [
        (m[1], m[2]) for m in map(_BASELINE_LINE.match, text.splitlines()) if m is not None
    ]
    start = text.rfind(_FIDUCIAL_SECTION)
    datum: list[str] = []
    if start >= 0:
        for line in text[start:].splitlines():
            m = _DATUM_LINE.match(line)
            if m:
                datum.append(m[1])
    return tuple(datum), baselines


def _east_north_mm(at: XYZ, delta: XYZ) -> tuple[float, float]:
    lat = math.atan2(at[2], math.hypot(at[0], at[1]))
    lon = math.atan2(at[1], at[0])
    east = -math.sin(lon) * delta[0] + math.cos(lon) * delta[1]
    north = (
        -math.sin(lat) * math.cos(lon) * delta[0]
        - math.sin(lat) * math.sin(lon) * delta[1]
        + math.cos(lat) * delta[2]
    )
    return east * 1000.0, north * 1000.0


def _shift_from(xyz: XYZ, others: list[XYZ]) -> tuple[float, float] | None:
    if len(others) < MIN_REFERENCE_DAYS:
        return None
    middle = tuple(statistics.median(p[i] for p in others) for i in range(3))
    return _east_north_mm(xyz, (xyz[0] - middle[0], xyz[1] - middle[1], xyz[2] - middle[2]))


def _shifts(
    doy: int, days: dict[int, dict[str, XYZ]]
) -> tuple[dict[str, tuple[float, float]], set[str]]:
    """Each station's shift on a day, against whichever side of it agrees better, and
    the stations that had only one side to compare with."""
    out: dict[str, tuple[float, float]] = {}
    single: set[str] = set()
    for station, xyz in days[doy].items():
        before = [
            days[d][station] for d in range(doy - WINDOW_DAYS, doy)
            if d in days and station in days[d]
        ]  # fmt: skip
        after = [
            days[d][station] for d in range(doy + 1, doy + WINDOW_DAYS + 1)
            if d in days and station in days[d]
        ]  # fmt: skip
        sides = [s for s in (_shift_from(xyz, before), _shift_from(xyz, after)) if s is not None]
        if sides:
            out[station] = min(sides, key=lambda s: math.hypot(*s))
            if len(sides) == 1:
                single.add(station)
    return out, single


def _split(
    shifts: dict[str, tuple[float, float]], baselines: list[tuple[str, str]]
) -> tuple[tuple[int, int], float, tuple[tuple[str, str], ...]] | None:
    """The two groups either side of the largest gap in the shifts, and what joins them."""
    # A small network can be suspect with fewer than MIN_GROUP stations moved.
    smallest = min(MIN_GROUP, math.ceil(SUSPECT_SHARE * len(shifts)))
    if len(shifts) < 2 * smallest:
        return None

    def widest(axis: int) -> tuple[float, int]:
        values = sorted(s[axis] for s in shifts.values())
        cuts = range(smallest, len(values) - smallest + 1)
        return max((values[i] - values[i - 1], i) for i in cuts)

    axis = max((0, 1), key=lambda a: widest(a)[0])
    cut = widest(axis)[1]
    ranked = sorted(shifts, key=lambda st: shifts[st][axis])
    values = [shifts[st][axis] for st in ranked]
    low, high = set(ranked[:cut]), set(ranked[cut:])
    separation = statistics.median(values[cut:]) - statistics.median(values[:cut])
    links = tuple(
        (a, b) for a, b in baselines if (a in low and b in high) or (a in high and b in low)
    )
    return (len(low), len(high)), separation, links


def _solved_days(year_dir: Path, year: int) -> dict[int, Path]:
    """The coordinate file of each solved day."""
    pattern = f"FIN_{year}[0-9][0-9][0-9]0.CRD"
    return {int(p.name[8:11]): p for p in (year_dir / "STA").glob(pattern)}


def check_year(year_dir: Path, year: int, doys: Iterable[int] | None = None) -> NetworkCheck:
    """Check the solved days of a year.

    ``year_dir`` holds STA/ and OUT/, as <result>/<campaign>/<year> does. ``doys`` limits
    which days are reported; the solved days around them are still used for comparison.
    """
    solved = _solved_days(year_dir, year)
    wanted = sorted(solved) if doys is None else sorted(set(doys))
    near = {d + k for d in wanted for k in range(-WINDOW_DAYS, WINDOW_DAYS + 1)}
    days = {d: read_crd(path) for d, path in solved.items() if d in near}

    result = NetworkCheck()
    for doy in wanted:
        shifts, single = _shifts(doy, days) if doy in days else ({}, set())
        if len(shifts) < MIN_STATIONS:
            result.not_checked.append(doy)
            continue
        result.checked.append(doy)
        moved_stations = [st for st, s in shifts.items() if math.hypot(*s) > MOVED_MM]
        moved = len(moved_stations)
        if moved / len(shifts) < SUSPECT_SHARE:
            continue
        one_sided = 2 * sum(st in single for st in moved_stations) > moved
        prc = year_dir / "OUT" / f"R2S_{year}{doy:03d}0.PRC"
        datum, baselines = read_prc(prc) if prc.is_file() else ((), [])
        split = _split(shifts, baselines)
        groups, separation, links = split if split is not None else (None, None, ())
        result.findings.append(
            DayFinding(doy, len(shifts), moved, datum, groups, separation, links, one_sided)
        )
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="bernese-check-network",
        description="Report solved days where part of the network shifted against the rest.",
    )
    ap.add_argument("--campaign", required=True, help="result campaign under $S, e.g. PHSUP")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--from", dest="doy_from", type=int, default=1)
    ap.add_argument("--to", dest="doy_to", type=int, default=366)
    ap.add_argument(
        "--year-dir", type=Path, help="the year's result directory; default $S/<campaign>/<year>"
    )
    args = ap.parse_args(argv)

    year_dir = args.year_dir
    if year_dir is None:
        savedisk = os.environ.get("S")
        if not savedisk:
            print("S is not set: source LOADGPS.setvar first, or pass --year-dir", file=sys.stderr)
            return 2
        year_dir = Path(savedisk) / args.campaign / str(args.year)

    solved = _solved_days(year_dir, args.year)
    wanted = [d for d in sorted(solved) if args.doy_from <= d <= args.doy_to]
    result = check_year(year_dir, args.year, wanted)
    for finding in result.findings:
        print(finding)
    span = f"DOY {args.doy_from:03d}-{args.doy_to:03d}"
    print(result.summary() if wanted else f"network check: no solved days in {span} of {year_dir}")
    if result.findings:
        return 1
    return 0 if result.checked else 2


if __name__ == "__main__":
    sys.exit(main())
