#!/usr/bin/env python3
"""Stage one year's daily observation files for a 5.4 run: links only, any year.

WHY NOT THE OTHER STAGING SCRIPTS
- stage_parity_2025.py is written around 2025 and the gps2 copy.
- stage_national_campaign.sh also installs the campaign's STA, BLQ and CRD from
  the as-fetched file-server metadata. Run against a campaign whose station
  files have since been corrected (PHSUP, PHNAT), it would replace them.

This one touches nothing but $D/<campaign>, and only adds links.

WHAT IS STAGED
Every daily file for the year, one per station-day:

- RINEX 2 from --rinex2 (a folder of the file-server copy: `<year>/` up to
  2023, the top level from 2024), names `ssssddd0.yyo`, `.yyd`, `.yyd.gz`.
- RINEX 3 long names from --rinex3 (default $D/RINEX3, where
  fetch_fiducial_obs.sh puts the IGS fiducials).

WHEN A STATION-DAY HAS MORE THAN ONE FILE
- RINEX 3 wins over RINEX 2, as RNX_COP's own priority list would have it and
  as the 2025 staging did.
- One observation in several packings counts as one station-day (65 of 2024,
  one of 2023). The most direct packing is linked: `.24o` as it is, else the
  Hatanaka-compressed `.24d.gz`, else `.24o.gz`.
- Two files in the same packing (differing only in letter case, say) are
  ambiguous, and the script refuses rather than choose.

Only daily files are linked: session character `0` for RINEX 2, `_01D_` for
RINEX 3, as RNX_COP globs. RINEX 2 links take an upper-case station code,
because RNX_COP globs on the code it is given; the source bytes are untouched.

Usage:
    scripts/stage_year_obs.py --year 2023 --campaign PHSUP \\
        --rinex2 /srv/gnss-archive/datapool/PHIVOLCS/2023              # dry run
    scripts/stage_year_obs.py --year 2023 --campaign PHSUP --rinex2 ... --apply
    ... --exclude PALA --exclude MABN        # stations to leave out
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sys
from pathlib import Path

Key = tuple[str, int]  # (station, day of year)


def patterns(year: int) -> tuple[re.Pattern, re.Pattern]:
    yy = f"{year % 100:02d}"
    rx2 = re.compile(rf"^([A-Za-z0-9]{{4}})(\d{{3}})0\.{yy}([oOdD])(\.gz|\.Z)?$")
    rx3 = re.compile(rf"^([A-Z0-9]{{4}})\S*_R_{year}(\d{{3}})\d{{4}}_01D_\S*[oO]\.(?i:rnx|crx)")
    return rx2, rx3


def index_dir(directory: Path, pattern: re.Pattern) -> dict[Key, list[Path]]:
    found: dict[Key, list[Path]] = collections.defaultdict(list)
    for path in sorted(directory.iterdir()):
        if m := pattern.match(path.name):
            found[(m[1].upper(), int(m[2]))].append(path)
    return found


def _rank(name: str, pattern: re.Pattern) -> int:
    """Lower is preferred: an observation file as it is, then Hatanaka-compressed
    (the form thousands of 2025 station-days ran from), then a gzipped observation file."""
    m = pattern.match(name)
    if m[3] in "oO":
        return 0 if not m[4] else 2
    return 1


def one_rinex2(files: list[Path], pattern: re.Pattern) -> Path | None:
    """The file to link for a station-day, or None when the choice is not clear.

    Several files for one station-day are normally one observation in several
    packings (`.24o`, `.24d.gz`, `.24o.gz`); the most direct packing is taken.
    Two files in the same packing (names differing in letter case) are None.
    """
    best = min(_rank(f.name, pattern) for f in files)
    top = [f for f in files if _rank(f.name, pattern) == best]
    return top[0] if len(top) == 1 else None


def choose(
    rx2: dict[Key, list[Path]], rx3: dict[Key, list[Path]], rx2_pattern: re.Pattern,
    first: int, last: int, exclude: set[str],
) -> tuple[dict[str, Path], collections.Counter, list[tuple[Key, list[str]]]]:
    """(link name -> source, counts by kind, ambiguous station-days)."""
    links: dict[str, Path] = {}
    used: collections.Counter = collections.Counter()
    ambiguous: list[tuple[Key, list[str]]] = []
    for key in sorted(set(rx2) | set(rx3)):
        code, doy = key
        if not first <= doy <= last or code in exclude:
            continue
        if key in rx3:
            if len(rx3[key]) > 1:
                ambiguous.append((key, [p.name for p in rx3[key]]))
                continue
            links[rx3[key][0].name] = rx3[key][0]
            used["RINEX 3"] += 1
            if key in rx2:
                used["RINEX 2 left out for a RINEX 3 file"] += 1
            continue
        src = one_rinex2(rx2[key], rx2_pattern)
        if src is None:
            ambiguous.append((key, [p.name for p in rx2[key]]))
            continue
        links[code + src.name[4:]] = src
        used["RINEX 2"] += 1
        if len(rx2[key]) > 1:
            used["other packings of a staged file left out"] += len(rx2[key]) - 1
    return links, used, ambiguous


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--campaign", required=True, help="links go to $D/<campaign>")
    ap.add_argument("--rinex2", type=Path, required=True, help="folder holding the year's RINEX 2 files")
    ap.add_argument("--rinex3", type=Path, help="folder holding RINEX 3 long-name files [default: $D/RINEX3]")
    ap.add_argument("--from", dest="first", type=int, default=1)
    ap.add_argument("--to", dest="last", type=int, default=366)
    ap.add_argument("--exclude", action="append", default=[], metavar="CODE",
                    help="a station to leave out (repeatable)")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    if "D" not in os.environ:
        print("refusing: $D is not set; source LOADGPS.setvar first", file=sys.stderr)
        return 1
    datapool = Path(os.environ["D"])
    dest = datapool / args.campaign
    rinex3_dir = args.rinex3 or datapool / "RINEX3"
    for d in (args.rinex2, rinex3_dir):
        if not d.is_dir():
            print(f"refusing: {d} is not a folder", file=sys.stderr)
            return 1
    rx2_pattern, rx3_pattern = patterns(args.year)
    exclude = {c.upper() for c in args.exclude}
    links, used, ambiguous = choose(
        index_dir(args.rinex2, rx2_pattern), index_dir(rinex3_dir, rx3_pattern),
        rx2_pattern, args.first, args.last, exclude,
    )
    stations = {(m[1].upper()) for n in links if (m := rx2_pattern.match(n) or rx3_pattern.match(n))}
    per_day = collections.Counter(
        int(m[2]) for n in links if (m := rx2_pattern.match(n) or rx3_pattern.match(n))
    )
    print(f"{args.campaign} {args.year} DOY {args.first}-{args.last}: {len(links):,} station-days, "
          f"{len(stations)} stations, {len(per_day)} days "
          f"({min(per_day.values(), default=0)} to {max(per_day.values(), default=0)} a day)")
    for kind, n in sorted(used.items()):
        print(f"  {n:>7,}  {kind}")
    if exclude:
        print(f"  excluded: {' '.join(sorted(exclude))}")
    for key, names in ambiguous:
        print(f"  AMBIGUOUS {key[0]} DOY {key[1]:03d}: {' '.join(names)}")
    if ambiguous:
        print("refusing: a station-day has more than one candidate file", file=sys.stderr)
        return 1
    if not links:
        print(f"refusing: no {args.year} daily files found", file=sys.stderr)
        return 1
    if not args.apply:
        print("Dry run: nothing written.")
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    blocked = [n for n in links if (dest / n).exists() and not (dest / n).is_symlink()]
    if blocked:
        print(f"refusing: {len(blocked)} link names are regular files in {dest}, "
              f"e.g. {blocked[0]}", file=sys.stderr)
        return 1
    made = kept = replaced = 0
    for name, src in sorted(links.items()):
        link = dest / name
        if link.is_symlink():
            if link.resolve() == src.resolve():
                kept += 1
                continue
            link.unlink()  # an earlier staging pointed it at another file
            replaced += 1
        link.symlink_to(src)
        made += 1
    stale = [
        path.name for path in sorted(dest.iterdir())
        if (m := rx2_pattern.match(path.name) or rx3_pattern.match(path.name))
        and args.first <= int(m[2]) <= args.last and path.name not in links
    ]
    print(f"{dest}: {made:,} links made ({replaced:,} repointed), {kept:,} already there")
    if stale:
        # RNX_COP takes everything in the directory, so these would run too.
        print(f"WARNING: {len(stale):,} files in {dest} for {args.year} DOY {args.first}-{args.last} "
              f"are not in this staging, e.g. {stale[0]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
