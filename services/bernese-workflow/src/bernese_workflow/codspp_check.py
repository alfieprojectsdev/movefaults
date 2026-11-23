"""Find stations a run dropped because their code positions made no sense.

WHY THIS EXISTS
A day can finish ok with a station quietly missing from it. Bernese's code-only
positioning step, CODSPP, rejects a station whose pseudoranges don't fit the orbits.
CODXTR then writes one line about it into the day's processing summary, and the
station is carried along without being estimated. Nothing fails.

In PHSUP 2023 that is how ISAB and ORAS went missing for months. Their old receivers
wrote files dated whole weeks early: ISAB 10 weeks, ORAS 4. The dates inside the
files agree with the wrong names, so no check of names, headers or first epochs can
see it. Only a position solved against the orbits of the claimed date fails. Their
days showed as ok throughout.

WHAT IT READS
The two CODXTR messages in each day's summary, OUT/R2S_<year><doy>0.PRC:

    ### PG CODXTR: NO RESULTS ARE AVAILABLE FOR STATION: ORAS ORAS
    ### PG CODXTR: NUMBER OF BAD OBS LARGER THAN 50% FOR STATION: ISAB ISAB
                   ...
                   BAD OBS:    57.10 %

and whether the day's coordinates, STA/FIN_<year><doy>0.CRD, estimated the station.
Usually it didn't: in PHSUP 2023 and 2024, 90 of 91 rejected station-days were carried
along unestimated. The exception, GUES on 2024 DOY 163 (78% bad), was still estimated,
so each line says how many of its days the station was actually missing.

WHAT IT DOESN'T DO
It doesn't say why. A wrong date gives this signature, and so does a receiver with
broken code data. PHSUP 2024 has BATU 100% bad on 20 days exactly a week apart
(DOY 084-217), which is not yet explained. It reads only saved files and changes nothing. A day with
no summary is counted as not checked, never as clean.

Usage:
    bernese-check-codspp --campaign PHSUP --year 2023
    bernese-check-codspp --campaign PHSUP --year 2024 --from 80 --to 170

Exit codes: 0 no station rejected, 1 at least one rejected, 2 nothing could be checked.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .network_check import read_crd

__all__ = ["CodsppCheck", "Rejection", "check_year", "main", "read_rejections"]

NO_RESULTS = "no_results"
BAD_OBS = "bad_obs"

_MESSAGE = re.compile(
    r"### PG CODXTR: (NO RESULTS ARE AVAILABLE|NUMBER OF BAD OBS LARGER THAN \d+%)"
    r" FOR STATION: (\S{4})"
)
_BAD_PCT = re.compile(r"^\s*BAD OBS:\s*([\d.]+)\s*%")


@dataclass(frozen=True)
class Rejection:
    """One station on one day."""

    station: str
    doy: int
    reason: str  # NO_RESULTS or BAD_OBS
    bad_pct: float | None = None  # for BAD_OBS, the share CODXTR printed
    estimated: bool | None = None  # in the day's solution; None when there is no CRD


def read_rejections(path: Path) -> dict[str, tuple[str, float | None]]:
    """Each station CODXTR rejected in one summary, with why.

    A station named by both messages counts as NO_RESULTS, the stronger of the two.
    CODXTR repeats a message for some stations; a repeat changes nothing.
    """
    out: dict[str, tuple[str, float | None]] = {}
    lines = path.read_text(errors="replace").splitlines()
    for i, line in enumerate(lines):
        m = _MESSAGE.search(line)
        if m is None:
            continue
        station = m[2]
        if m[1].startswith("NO RESULTS"):
            out[station] = (NO_RESULTS, None)
            continue
        if out.get(station, ("",))[0] == NO_RESULTS:
            continue
        # The share follows the FILE line, within the next few lines.
        pct = None
        for follow in lines[i + 1 : i + 4]:
            p = _BAD_PCT.match(follow)
            if p:
                pct = float(p[1])
                break
        out[station] = (BAD_OBS, pct)
    return out


def _ranges(doys: Iterable[int]) -> str:
    """001-028, 053, 069 for a sorted run of days."""
    out: list[str] = []
    days = sorted(set(doys))
    i = 0
    while i < len(days):
        j = i
        while j + 1 < len(days) and days[j + 1] == days[j] + 1:
            j += 1
        out.append(f"{days[i]:03d}" if i == j else f"{days[i]:03d}-{days[j]:03d}")
        i = j + 1
    return ", ".join(out)


def _days(n: int) -> str:
    return f"{n} day{'' if n == 1 else 's'}"


@dataclass
class CodsppCheck:
    """What a check looked at, so that nothing unchecked reads as clean."""

    checked: list[int] = field(default_factory=list)
    not_checked: list[int] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)

    def by_station(self) -> dict[str, list[Rejection]]:
        """Rejections per station, the most often rejected first."""
        out: dict[str, list[Rejection]] = {}
        for r in sorted(self.rejections, key=lambda r: (r.station, r.doy)):
            out.setdefault(r.station, []).append(r)
        return dict(sorted(out.items(), key=lambda kv: (-len(kv[1]), kv[0])))

    def station_lines(self) -> list[str]:
        """One line per rejected station, as the CLI prints them."""
        lines = []
        for station, rs in self.by_station().items():
            no_res = sum(r.reason == NO_RESULTS for r in rs)
            bad = [r for r in rs if r.reason == BAD_OBS]
            parts = []
            if no_res:
                parts.append(f"no code solution on {no_res}")
            if bad:
                pcts = [r.bad_pct for r in bad if r.bad_pct is not None]
                lo, hi = (f"{min(pcts):.0f}", f"{max(pcts):.0f}") if pcts else ("", "")
                span = "" if not pcts else f", {lo}% bad" if lo == hi else f", {lo}-{hi}% bad"
                parts.append(f"over 50% bad observations on {len(bad)}{span}")
            known = [r for r in rs if r.estimated is not None]
            dropped = sum(r.estimated is False for r in known)
            if known:
                parts.append(f"not in the solution on {dropped} of {len(known)}")
            lines.append(
                f"{station}: rejected by CODSPP on {_days(len(rs))} "
                f"(DOY {_ranges(r.doy for r in rs)}): " + "; ".join(parts)
            )
        return lines

    def summary(self) -> str:
        """One line for a run's result."""
        if not self.checked:
            return f"CODSPP check: none of {_days(len(self.not_checked))} could be checked"
        stations = self.by_station()
        if stations:
            named = ", ".join(f"{s} ({len(rs)})" for s, rs in list(stations.items())[:5])
            more = f" and {len(stations) - 5} more" if len(stations) > 5 else ""
            text = (
                f"CODSPP check: {len(stations)} station(s) rejected over "
                f"{_days(len(self.checked))}: {named}{more}"
            )
        else:
            text = f"CODSPP check: {_days(len(self.checked))} checked, no station rejected"
        if self.not_checked:
            text += f"; {_days(len(self.not_checked))} not checked"
        return text


def _summaries(year_dir: Path, year: int) -> dict[int, Path]:
    pattern = f"R2S_{year}[0-9][0-9][0-9]0.PRC"
    return {int(p.name[8:11]): p for p in (year_dir / "OUT").glob(pattern)}


def check_year(year_dir: Path, year: int, doys: Iterable[int] | None = None) -> CodsppCheck:
    """Check the days of a year that have a processing summary.

    ``year_dir`` holds OUT/ and STA/, as <result>/<campaign>/<year> does. ``doys``
    limits the days; one of them without a summary is counted as not checked.
    """
    found = _summaries(year_dir, year)
    wanted = sorted(found) if doys is None else sorted(set(doys))
    result = CodsppCheck()
    for doy in wanted:
        prc = found.get(doy)
        if prc is None:
            result.not_checked.append(doy)
            continue
        result.checked.append(doy)
        rejected = read_rejections(prc)
        if not rejected:
            continue
        crd = year_dir / "STA" / f"FIN_{year}{doy:03d}0.CRD"
        estimated = set(read_crd(crd)) if crd.is_file() else None
        for station, (reason, pct) in rejected.items():
            result.rejections.append(
                Rejection(
                    station,
                    doy,
                    reason,
                    pct,
                    None if estimated is None else station in estimated,
                )  # fmt: skip
            )
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="bernese-check-codspp",
        description="Report stations a run dropped because CODSPP rejected their code data.",
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

    found = _summaries(year_dir, args.year)
    wanted = [d for d in sorted(found) if args.doy_from <= d <= args.doy_to]
    if not wanted:
        span = f"DOY {args.doy_from:03d}-{args.doy_to:03d}"
        print(f"CODSPP check: no processing summaries in {span} of {year_dir}")
        return 2
    result = check_year(year_dir, args.year, wanted)
    for line in result.station_lines():
        print(line)
    print(result.summary())
    return 1 if result.rejections else 0


if __name__ == "__main__":
    sys.exit(main())
