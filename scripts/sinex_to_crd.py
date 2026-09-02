#!/usr/bin/env python3
"""Convert a SINEX solution to a Bernese CRD file.

WHY THIS EXISTS
PHIVOLCS' 2025 weekly solutions are retained as SINEX only; there are no CRD
files and no per-site ENU series on the file server. To plot her series against
ours, hers has to enter the SAME chain ours does -- `crd-to-plots` consumes
CRD, so the SINEX becomes CRD first.

That both sides then go through one identical implementation is the point, not
a workaround. Had her PLOT files been available we would be comparing her
processing chain AND her solutions at once, with no way to separate them. This
way any difference in the plot is a difference in the SOLUTIONS.

THE EPOCH MATTERS MORE THAN IT LOOKS
`crd_pipeline` dates a CRD from its `EPOCH:` header, and that date becomes the
decimal year on the plot. A SINEX carries a start and an end epoch; the CRD
gets the MIDPOINT, which is what a weekly solution's coordinate actually
refers to. Using the start would shift her series 3.5 days earlier than ours
and show up as a constant offset that is not real.

Usage:
    scripts/sinex_to_crd.py WK_2375.SNX -o WK_2375.CRD
    scripts/sinex_to_crd.py ~/phivolcs-weekly/*.SNX --out-dir ~/phivolcs-crd
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

HDR = re.compile(
    r"^%=SNX\s+\S+\s+\S+\s+\S+\s+\S+\s+"
    r"(\d{2}):(\d{3}):(\d{5})\s+(\d{2}):(\d{3}):(\d{5})"
)


def yds_to_dt(yy: str, doy: str, sod: str) -> datetime:
    """SINEX YY:DOY:SOD -> datetime. Two-digit year, IGS convention."""
    y = int(yy)
    y += 2000 if y < 80 else 1900
    return datetime(y, 1, 1) + timedelta(days=int(doy) - 1, seconds=int(sod))


def parse(path: Path) -> tuple[datetime, list[tuple[str, str, float, float, float]]]:
    lines = path.read_text(errors="replace").splitlines()
    if not lines:
        raise ValueError(f"{path.name}: empty")

    m = HDR.match(lines[0])
    if not m:
        raise ValueError(f"{path.name}: unparseable SINEX header line")
    start = yds_to_dt(*m.group(1, 2, 3))
    end = yds_to_dt(*m.group(4, 5, 6))
    # Midpoint: the epoch a multi-day solution's coordinate refers to.
    epoch = start + (end - start) / 2

    domes: dict[str, str] = {}
    inblk = False
    for line in lines:
        if line.startswith("+SITE/ID"):
            inblk = True
            continue
        if line.startswith("-SITE/ID"):
            break
        if inblk and re.match(r"^ [A-Z0-9]{4} ", line):
            f = line.split()
            domes[f[0].upper()] = f[2] if len(f) > 2 and re.match(r"^\d{5}[A-Z]", f[2]) else ""

    comp: dict[str, dict[str, float]] = {}
    inblk = False
    for line in lines:
        if line.startswith("+SOLUTION/ESTIMATE"):
            inblk = True
            continue
        if line.startswith("-SOLUTION/ESTIMATE"):
            break
        if not inblk or line.startswith("*"):
            continue
        f = line.split()
        if len(f) < 9 or f[1] not in ("STAX", "STAY", "STAZ"):
            continue
        try:
            comp.setdefault(f[2].upper(), {})[f[1]] = float(f[8])
        except ValueError:
            continue

    # All three components or the station is dropped: a partial coordinate
    # would silently become a wrong one.
    out = []
    for s in sorted(comp):
        v = comp[s]
        if {"STAX", "STAY", "STAZ"} <= v.keys():
            out.append((s, domes.get(s, ""), v["STAX"], v["STAY"], v["STAZ"]))
    if not out:
        raise ValueError(f"{path.name}: no complete station coordinates")
    return epoch, out


def write_crd(path: Path, epoch: datetime, rows, title: str) -> None:
    L = [
        f"{title:<64}{epoch:%d-%b-%y %H:%M}".upper()[:80],
        "-" * 80,
        f"LOCAL GEODETIC DATUM: IGS20             "
        f"EPOCH: {epoch:%Y-%m-%d %H:%M:%S}",
        "",
        "NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG",
        "",
    ]
    for i, (site, dome, x, y, z) in enumerate(rows, 1):
        name = f"{site} {dome}".strip()
        # Every station in a SINEX SOLUTION/ESTIMATE block WAS estimated, so
        # each row carries the flags that mark it as such. Without them
        # read_crd_file(estimated_only=True) discards the whole file as a
        # priori carry-through.
        L.append(f"{i:>3}  {name:<16}{x:>15.5f}{y:>15.5f}{z:>15.5f}    A      G")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sinex", type=Path, nargs="+")
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--out-dir", type=Path)
    args = ap.parse_args()

    if args.output and len(args.sinex) > 1:
        print("-o takes a single input; use --out-dir for many", file=sys.stderr)
        return 2
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    ok = bad = 0
    for src in args.sinex:
        try:
            epoch, rows = parse(src)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
            print(f"  SKIP {src.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            bad += 1
            continue
        dst = args.output or ((args.out_dir or src.parent) / (src.stem + ".CRD"))
        write_crd(dst, epoch, rows, src.stem)
        print(f"  {src.name} -> {dst.name}  {len(rows)} stations  epoch {epoch:%Y-%m-%d %H:%M}")
        ok += 1
    print(f"  converted {ok}, skipped {bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
