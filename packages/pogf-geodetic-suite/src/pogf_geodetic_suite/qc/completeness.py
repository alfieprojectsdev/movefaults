"""
RINEX data-completeness scan — which days can be processed, before staging them.

WHY THIS EXISTS, AND WHY IT RUNS *BEFORE* `stage_luzon_campaign.sh`
-------------------------------------------------------------------
The 2025 national run lost 8 of 365 days. Six of those failed for one reason:
**fewer than three reference stations**, which is below the minimum for a
Helmert transformation, so there was no way to tie the day to the frame.

Every one of those days was discovered *by failing a BPE run* — roughly two
minutes of R740 time each, plus the analyst attention to work out why. The
information needed to predict all of them was already sitting on disk in the
datapool. Nobody had asked.

This module asks. Same question the legacy checker asked
(`analysis/10 RINEX Checker/`, Kurt, 2024), moved one step earlier in the
pipeline and given the two things it was missing:

* **RINEX 3.** The legacy checker matches ``.YYo`` / ``.YYO`` only. Every IGS
  fiducial is RINEX 3, so the checker could not see the very stations whose
  absence caused the failures.
* **A per-day view.** Per-station coverage answers "is ALCO complete?".
  Per-day counts answer "can DOY 059 be processed at all?", which is the
  question staging needs.

Exit codes are meant for scripting:

===  ==========================================================
  0  every day in range meets the minimum
  1  at least one day is short — the run will lose those days
  2  nothing found to scan
===  ==========================================================
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import click

# The IGS fiducials fetched by scripts/fetch_fiducial_obs.sh. Kept as 4-char
# codes because that is what both RINEX 2 and RINEX 3 filenames start with.
DEFAULT_REFERENCE_STATIONS = ("AIRA", "ALIC", "DAEJ", "DARW", "MCIL", "PIMO", "PNGM")

# Minimum reference stations for a Helmert transformation. Three is the floor,
# not a comfortable number: it leaves zero redundancy, so one bad station takes
# the day with it. See SESSION_LOG_20260729_storage.md §24.1.
DEFAULT_MIN_REFERENCES = 3

# RINEX 2:  SSSSDDD0.YYo  — also .YYO, Hatanaka .YYd/.YYD, optionally compressed
_RINEX2 = re.compile(
    r"^(?P<sta>[A-Za-z0-9]{4})(?P<doy>\d{3})[0-9A-Za-z]\.(?P<yy>\d{2})(?P<kind>[oOdD])"
    r"(?:\.(?:gz|Z|bz2))?$"
)

# RINEX 3:  SSSSMRCCC_R_YYYYDDDHHMM_01D_30S_MO.rnx  — also .crx, compressed
_RINEX3 = re.compile(
    r"^(?P<sta>[A-Za-z0-9]{4})\d{2}[A-Za-z]{3}_[A-Za-z]_(?P<yyyy>\d{4})(?P<doy>\d{3})\d{4}"
    r"_.*?\.(?:rnx|crx)(?:\.(?:gz|Z|bz2))?$",
    re.IGNORECASE,
)


def is_leap_year(year: int) -> bool:
    """Proleptic Gregorian leap year.

    The legacy checker used ``year % 4 == 0``, which is wrong for 1900 and
    2100. Harmless for the data we hold and wrong the moment somebody scans a
    century boundary, so it is fixed here rather than carried forward.
    """
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_in_year(year: int) -> int:
    return 366 if is_leap_year(year) else 365


def compress_ranges(values: list[int]) -> str:
    """``[1,2,3,5,9,10]`` -> ``'001-003, 005, 009-010'``.

    Port of the legacy ``get_line_numbers_concat``. Zero-padded to three
    digits because these are day-of-year numbers and ``9`` next to ``100`` in
    the same line is hard to read.
    """
    if not values:
        return ""
    out: list[str] = []
    run_start = prev = values[0]
    for v in values[1:]:
        if v == prev + 1:
            prev = v
            continue
        out.append(f"{run_start:03d}" if run_start == prev else f"{run_start:03d}-{prev:03d}")
        run_start = prev = v
    out.append(f"{run_start:03d}" if run_start == prev else f"{run_start:03d}-{prev:03d}")
    return ", ".join(out)


@dataclass
class Coverage:
    """What was found on disk for one year."""

    year: int
    #: station code -> set of DOYs present
    by_station: dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))
    #: DOY -> set of station codes present
    by_day: dict[int, set[str]] = field(default_factory=lambda: defaultdict(set))
    #: files that looked like RINEX but did not parse
    unparsed: list[str] = field(default_factory=list)

    @property
    def stations(self) -> list[str]:
        return sorted(self.by_station)

    def gaps(self, station: str) -> list[int]:
        """DOYs in the year for which this station has no file."""
        present = self.by_station.get(station, set())
        return [d for d in range(1, days_in_year(self.year) + 1) if d not in present]

    def short_days(
        self,
        reference_stations: tuple[str, ...],
        minimum: int,
        doy_from: int = 1,
        doy_to: int | None = None,
    ) -> list[tuple[int, int, list[str]]]:
        """Days whose reference-station count is below ``minimum``.

        Returns ``(doy, count, present_references)``, which is the list that
        predicts what a run will lose. Days with *no* data at all are included:
        a day absent from the datapool is as unprocessable as a short one, and
        conflating "short" with "missing" is how DOY 139 (one station) ended up
        in the same bucket as DOY 058-061 (too few references).
        """
        refs = {s.upper() for s in reference_stations}
        last = doy_to if doy_to is not None else days_in_year(self.year)
        short: list[tuple[int, int, list[str]]] = []
        for doy in range(doy_from, last + 1):
            present = sorted(self.by_day.get(doy, set()) & refs)
            if len(present) < minimum:
                short.append((doy, len(present), present))
        return short


def scan(root: Path, year: int) -> Coverage:
    """Walk ``root`` and record which station-days are present for ``year``.

    Subdirectories are included, matching the legacy checker's behaviour — the
    datapool nests by station and by day depending on which era wrote it.
    """
    cov = Coverage(year=year)
    yy = year % 100
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        m2 = _RINEX2.match(name)
        if m2 is not None:
            if int(m2.group("yy")) != yy:
                continue
            cov.by_station[m2.group("sta").upper()].add(int(m2.group("doy")))
            cov.by_day[int(m2.group("doy"))].add(m2.group("sta").upper())
            continue
        m3 = _RINEX3.match(name)
        if m3 is not None:
            if int(m3.group("yyyy")) != year:
                continue
            cov.by_station[m3.group("sta").upper()].add(int(m3.group("doy")))
            cov.by_day[int(m3.group("doy"))].add(m3.group("sta").upper())
            continue
        # Only complain about things that look like they were meant to be RINEX.
        if re.search(r"\.\d{2}[oOdD](\.(gz|Z|bz2))?$|\.(rnx|crx)(\.(gz|Z|bz2))?$", name):
            cov.unparsed.append(str(path))
    return cov


@click.command()
@click.argument("root", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--year", "-y", required=True, type=int, help="Four-digit year to scan.")
@click.option("--from", "doy_from", default=1, type=int, help="First DOY (default 1).")
@click.option("--to", "doy_to", default=None, type=int, help="Last DOY (default end of year).")
@click.option(
    "--min-references",
    default=DEFAULT_MIN_REFERENCES,
    type=int,
    help=f"Minimum reference stations per day (default {DEFAULT_MIN_REFERENCES}).",
)
@click.option(
    "--reference",
    "references",
    multiple=True,
    help="Reference station code; repeatable. Defaults to the IGS fiducial set.",
)
@click.option("--per-station/--no-per-station", default=True, help="Show per-station gaps.")
def main(
    root: Path,
    year: int,
    doy_from: int,
    doy_to: int | None,
    min_references: int,
    references: tuple[str, ...],
    per_station: bool,
) -> None:
    """Scan ROOT for RINEX data completeness in a given year.

    Run this BEFORE staging a campaign. It answers, from the datapool alone,
    which days cannot be processed — which is otherwise learned by failing a
    BPE run on each of them.
    """
    refs = tuple(r.upper() for r in references) or DEFAULT_REFERENCE_STATIONS
    cov = scan(root, year)

    if not cov.by_station:
        click.echo(f"No RINEX files found for {year} under {root}", err=True)
        raise SystemExit(2)

    last = doy_to if doy_to is not None else days_in_year(year)
    click.echo(f"=== RINEX completeness: {year} DOY {doy_from:03d}-{last:03d} ===")
    click.echo(f"root       : {root}")
    click.echo(f"stations   : {len(cov.stations)}")
    click.echo(f"references : {', '.join(refs)} (minimum {min_references}/day)")

    if per_station:
        click.echo("\n-- per station --")
        total = last - doy_from + 1
        for sta in cov.stations:
            present = {d for d in cov.by_station[sta] if doy_from <= d <= last}
            missing = [d for d in range(doy_from, last + 1) if d not in present]
            mark = "*" if sta in refs else " "
            click.echo(f"{mark}{sta}  {len(present):3d}/{total:3d}", nl=False)
            click.echo(f"  missing: {compress_ranges(missing)}" if missing else "  complete")

    short = cov.short_days(refs, min_references, doy_from, last)
    click.echo("\n-- days that cannot be processed --")
    if not short:
        click.echo(f"none: every day has at least {min_references} reference stations")
    else:
        for doy, count, present in short:
            have = ", ".join(present) if present else "none"
            click.echo(f"  DOY {doy:03d}  {count} reference station(s): {have}")
        click.echo(f"\n{len(short)} day(s) short. These will fail if staged: {compress_ranges([d for d, _, _ in short])}")

    if cov.unparsed:
        click.echo(f"\n{len(cov.unparsed)} RINEX-looking file(s) did not parse; first few:", err=True)
        for p in cov.unparsed[:5]:
            click.echo(f"  {p}", err=True)

    raise SystemExit(1 if short else 0)


if __name__ == "__main__":
    main()
