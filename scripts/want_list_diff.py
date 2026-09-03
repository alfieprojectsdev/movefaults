#!/usr/bin/env python3
"""
Which want-list site-years does a drive actually close?

`gnss_want_list.py` says what the processing team recorded as missing: 955
site-years across 271 sites, 1994-2019. This answers the other half — given a
list of file paths from a drive, which of those site-years are present on it.

USAGE
    find /run/media/finch/HD-LBU2 -type f > /tmp/files.txt
    python3 scripts/want_list_diff.py /tmp/files.txt --label HD-LBU2

Reads paths from a file (one per line) rather than walking itself, because the
walk over a slow USB volume takes minutes and is worth doing once and reusing.

WHAT IT MATCHES, AND WHAT IT CANNOT
------------------------------------
RINEX 2 short names, `SSSSDDDS.YYt`:

    pimo1190.11o.gz  ->  site PIMO, DOY 119, year 2011, observation
    SOMA2961.07O     ->  site SOMA, DOY 296, year 2007

That is the dominant convention on these drives and it carries site and year in
the name, which is exactly what the want-list is keyed on.

**Raw receiver files usually do not.** Trimble `.T02` and Leica `.mNN` names are
receiver-assigned — `SABL083aB.T02` happens to carry a site prefix because
somebody named the directory well, but that is a local convention, not a
standard. Those are counted separately and reported as *unresolved*, never
silently dropped: a raw file that cannot be attributed is still data, and
pretending otherwise would overstate what is missing.

The two-digit year uses the RINEX convention: 80-99 -> 19xx, 00-79 -> 20xx.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WANT_CSV = REPO / "docs" / "bern52" / "gnss_want_list.csv"

# SSSSDDDS.YYt  — site(4) doy(3) session(1) . year(2) type(1)
_RINEX2 = re.compile(
    r"^(?P<site>[A-Za-z0-9]{4})(?P<doy>\d{3})(?P<sess>[0-9A-Za-z])\."
    r"(?P<yy>\d{2})(?P<kind>[odngmODNGM])(?:\.(?:gz|Z|zip))?$"
)
# RINEX 3 long name — carries the site and a full year
_RINEX3 = re.compile(
    r"^(?P<site>[A-Za-z0-9]{4})\d{2}[A-Za-z]{3}_[A-Za-z]_(?P<yyyy>\d{4})\d{3}",
    re.IGNORECASE,
)
_RAW = re.compile(r"\.(t0[0-9]|tgd|m[0-9]{2})$", re.IGNORECASE)

# Raw receiver files are receiver-named, but PHIVOLCS' download tooling has
# used two conventions that DO carry the site. Both were found on DATA0, where
# 60,951 raw files would otherwise have been unattributable:
#
#   BASC201110260000A.T02   site + YYYYMMDD + HHMM   -> site and year in the name
#   JOSE330bC.T02           site + DOY + session     -> site in the name, year NOT
#   LAGW190a.m00            same, Leica              -> year NOT
#   36252110.t01            receiver serial          -> neither; unattributable
#
# The second form takes its year from the enclosing directory (`RAW/2017/`),
# which is how the download tool laid them out. That is a local convention,
# not a standard, so it is applied ONLY when the parent directory is a bare
# 4-digit year -- guessing a year from a deeper path would invent coverage.
_RAW_DATED = re.compile(
    r"^(?P<site>[A-Z0-9]{4})(?P<yyyy>(?:19|20)\d{2})[01]\d[0-3]\d",
    re.IGNORECASE,
)
_RAW_DOY = re.compile(
    r"^(?P<site>[A-Z]{3}[A-Z0-9])(?P<doy>\d{3})[a-z0-9]*\.(?:t0[0-9]|m[0-9]{2}|tgd)$",
    re.IGNORECASE,
)
_YEAR_DIR = re.compile(r"^(19|20)\d{2}$")


def rinex_year(yy: int) -> int:
    """RINEX two-digit year: 80-99 -> 19xx, else 20xx."""
    return 1900 + yy if yy >= 80 else 2000 + yy


def load_want() -> set[tuple[str, int]]:
    if not WANT_CSV.exists():
        sys.exit(
            f"{WANT_CSV.relative_to(REPO)} not found. Generate it first:\n"
            "  python3 scripts/gnss_want_list.py"
        )
    want: set[tuple[str, int]] = set()
    with WANT_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            site = (row.get("site") or "").strip().upper()
            year = (row.get("year") or "").strip()
            if site and year.isdigit():
                want.add((site, int(year)))
    return want


def scan_paths(path_file: Path) -> tuple[set[tuple[str, int]], int, int]:
    """Return (present site-years, matched files, unresolved raw files)."""
    present: set[tuple[str, int]] = set()
    matched = 0
    raw_unresolved = 0
    with path_file.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            name = line.rstrip("\n").rsplit("/", 1)[-1]
            m = _RINEX2.match(name)
            if m:
                present.add((m.group("site").upper(), rinex_year(int(m.group("yy")))))
                matched += 1
                continue
            m3 = _RINEX3.match(name)
            if m3:
                present.add((m3.group("site").upper(), int(m3.group("yyyy"))))
                matched += 1
                continue
            if _RAW.search(name):
                md = _RAW_DATED.match(name)
                if md:
                    present.add((md.group("site").upper(), int(md.group("yyyy"))))
                    matched += 1
                    continue
                mdoy = _RAW_DOY.match(name)
                if mdoy:
                    # Year from the enclosing directory, only when it is a bare
                    # year. Anything else and the file stays unresolved.
                    parts = line.rstrip("\n").split("/")
                    parent = parts[-2] if len(parts) >= 2 else ""
                    if _YEAR_DIR.match(parent):
                        present.add((mdoy.group("site").upper(), int(parent)))
                        matched += 1
                        continue
                raw_unresolved += 1
    return present, matched, raw_unresolved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path_file", type=Path, help="File containing one path per line.")
    ap.add_argument("--label", default=None, help="Drive name, for the report header.")
    ap.add_argument("--show", type=int, default=25, help="Rows to print per table.")
    args = ap.parse_args()

    want = load_want()
    present, matched, raw_unresolved = scan_paths(args.path_file)

    closes = want & present
    still_missing = want - present
    label = args.label or args.path_file.name

    want_sites = {s for s, _ in want}
    closed_sites = {s for s, _ in closes}

    print(f"=== want-list diff: {label} ===")
    print(f"  want-list          : {len(want):5d} site-years across {len(want_sites)} sites")
    print(f"  on this drive      : {len(present):5d} site-years "
          f"({matched:,} files matched a RINEX name)")
    print(f"  CLOSES             : {len(closes):5d} site-years across {len(closed_sites)} sites")
    print(f"  still missing      : {len(still_missing):5d} site-years")
    if raw_unresolved:
        print(f"  unresolved raw     : {raw_unresolved:,} files "
              "(.T0x/.mNN — receiver-named, no site/year in the filename)")

    if closes:
        by_site: dict[str, list[int]] = defaultdict(list)
        for s, y in closes:
            by_site[s].append(y)
        print(f"\n-- closed, most first ({min(args.show, len(by_site))} of {len(by_site)} sites) --")
        for site, years in sorted(by_site.items(), key=lambda kv: (-len(kv[1]), kv[0]))[: args.show]:
            print(f"  {site}  {len(years):3d}  {', '.join(str(y) for y in sorted(years))}")

    if still_missing:
        rest: dict[str, list[int]] = defaultdict(list)
        for s, y in still_missing:
            rest[s].append(y)
        print(f"\n-- still missing, most first ({min(args.show, len(rest))} of {len(rest)} sites) --")
        for site, years in sorted(rest.items(), key=lambda kv: (-len(kv[1]), kv[0]))[: args.show]:
            print(f"  {site}  {len(years):3d}  {', '.join(str(y) for y in sorted(years))}")

    # Sites present on the drive that the want-list never asked for. Not a
    # finding in itself -- most are IGS fiducials -- but a site here that IS a
    # PHIVOLCS code means the inventory's picture is incomplete.
    extra_sites = {s for s, _ in present} - want_sites
    if extra_sites:
        print(f"\n-- on the drive but not in the want-list: {len(extra_sites)} sites --")
        print("  " + ", ".join(sorted(extra_sites)[:40]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
