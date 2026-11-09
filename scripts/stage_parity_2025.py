#!/usr/bin/env python3
"""Stage gps2's 2025 RINEX for a 5.4 run: the 5.2 run's station set, or every file on hand.

TWO MODES
Default (PHPAR, the parity run): each day gets the stations in that day's gps2
final solution, and no others, so the 5.4 and 5.2 runs solve the same network.
RNX_COP takes every station in V_RNXDIR, so what is in the directory is what
runs. The files gps2 holds but its solutions left out (all of PALA, for one)
stay in the copy and out of the run.

--all (PHSUP, the superset run): every daily file in the gps2 copy, whether or
not the 5.2 solutions used it, plus any station-day the copy lacks that gps3's
own $D/RINEX3 holds (14 days of PNGM as of 2026-11-07). The gps2 copy wins
wherever both have a station-day, so gps3's files only fill gaps. Expect 5.4 to
drop some of the extra station-days: several were left out of the 5.2 run for a
reason (PALA fails RNXGRA on the days whose logs survive).

WHICH FILE, WHEN A STATION-DAY HAS BOTH FORMATS
RINEX 3. On 680 solved station-days (DAEJ, PTAG, PPPC) gps2 holds both. The RAW
file its run left for DAEJ, PTAG and PPPC on DOY 361 is RINEX 3.02, and RNX_COP's
own priority list ("R","r","S","s","U","u","short","rx2") would pick it too.

Only daily observation files are linked: the long-name pattern requires `_01D_`
and an observation suffix (`...O.rnx`/`...O.crx`), as RNX_COP's glob does, so
CLAV's nine partial files and any navigation files stay out in both modes.

The links keep the source bytes: nothing is converted here. RINEX 2 links take
an upper-case station code because RNX_COP globs on the code it is given.

Usage:
    scripts/stage_parity_2025.py --from 194 --to 200                  # dry run
    scripts/stage_parity_2025.py --from 1 --to 365 --apply
    scripts/stage_parity_2025.py --campaign PHSUP --all --from 1 --to 365 --apply
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sys
from pathlib import Path

COPY = Path("/srv/gnss-archive/parity_2025")
BY_DAY = Path.home() / "gps2_2025_bsw52_20261106" / "stations_by_day.tsv"
RX2 = re.compile(r"^([A-Za-z0-9]{4})(\d{3})0\.25[oOdD](\.gz)?$")
RX3 = re.compile(r"^([A-Z0-9]{4})\S*_R_2025(\d{3})\d{4}_01D_\S*[oO]\.(?i:rnx|crx)")


def index_dir(directory: Path, pattern: re.Pattern, upper: bool) -> dict:
    found: dict[tuple[str, int], list[Path]] = collections.defaultdict(list)
    for path in sorted(directory.iterdir()):
        if m := pattern.match(path.name):
            found[(m[1].upper() if upper else m[1], int(m[2]))].append(path)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="first", type=int, required=True)
    ap.add_argument("--to", dest="last", type=int, required=True)
    ap.add_argument("--campaign", default="PHPAR", help="links go to $D/<campaign>")
    ap.add_argument("--all", action="store_true",
                    help="every daily file on hand, not only the 5.2 run's solved station-days")
    ap.add_argument("--as-gps2", action="append", default=[], metavar="CODE",
                    help="with --all: stage CODE only on the days gps2's solutions "
                         "used it (repeatable); --apply also removes its other links")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    as_gps2 = {c.upper() for c in args.as_gps2}
    if as_gps2 and not args.all:
        ap.error("--as-gps2 only makes sense with --all")

    dest = Path(os.environ["D"]) / args.campaign
    rx2 = index_dir(COPY / "PHIVOLCS_2025", RX2, upper=True)
    rx3 = index_dir(COPY / "RINEX3_2025", RX3, upper=False)
    gps2_days = set()
    for line in BY_DAY.read_text().splitlines():
        doy, code = line.split("\t")
        gps2_days.add((code, int(doy)))
    gap_fill: dict = {}
    if args.all:
        wanted = sorted(set(rx2) | set(rx3))
        gps3_rx3 = index_dir(Path(os.environ["D"]) / "RINEX3", RX3, upper=False)
        gap_fill = {k: v for k, v in gps3_rx3.items() if k not in rx2 and k not in rx3}
        wanted = sorted(set(wanted) | set(gap_fill))
        # A station whose data mostly fails preprocessing (MABN from DOY 017)
        # stops the run on each such day; gps2 left it out on those days.
        wanted = [k for k in wanted if k[0] not in as_gps2 or k in gps2_days]
    else:
        wanted = sorted(gps2_days)

    links: dict[str, Path] = {}
    missing, ambiguous = [], []
    used = collections.Counter()
    for key in wanted:
        if not args.first <= key[1] <= args.last:
            continue
        for source, label in ((rx3, "RINEX 3"), (gap_fill, "RINEX 3, gps3 gap fill")):
            if key in source:
                if len(source[key]) > 1:
                    ambiguous.append((key, [p.name for p in source[key]]))
                else:
                    links[source[key][0].name] = source[key][0]
                    used[label] += 1
                break
        else:
            if key in rx2:
                if len(rx2[key]) > 1:
                    ambiguous.append((key, [p.name for p in rx2[key]]))
                    continue
                src = rx2[key][0]
                links[key[0] + src.name[4:]] = src
                used["RINEX 2"] += 1
            else:
                missing.append(key)

    print(f"{args.campaign} DOY {args.first}-{args.last}: "
          f"{sum(used.values()):,} station-days {dict(used)}")
    for item in missing:
        print(f"  MISSING {item}")
    for item in ambiguous:
        print(f"  AMBIGUOUS {item}")
    if missing or ambiguous:
        print("refusing: a wanted station-day has no single file", file=sys.stderr)
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
    removed = 0
    for path in sorted(dest.iterdir()) if as_gps2 else []:
        m = RX2.match(path.name) or RX3.match(path.name)
        if (m and m[1].upper() in as_gps2 and int(m[2]) in range(args.first, args.last + 1)
                and path.name not in links and path.is_symlink()):
            path.unlink()
            removed += 1
    stale = [
        path.name for path in sorted(dest.iterdir())
        if (m := RX2.match(path.name) or RX3.match(path.name))
        and args.first <= int(m[2]) <= args.last and path.name not in links
    ]
    print(f"{dest}: {made:,} links made ({replaced:,} repointed), {kept:,} already there, "
          f"{removed:,} removed")
    if stale:
        # RNX_COP takes everything in the directory, so these would run too.
        print(f"WARNING: {len(stale):,} files in {dest} for DOY {args.first}-{args.last} "
              f"are not in this staging, e.g. {stale[0]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
