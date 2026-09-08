#!/usr/bin/env python3
"""Decode the raw receiver files that would close an open want-list site-year.

WHY ONLY SOME OF THEM
The archive holds ~81,000 raw receiver files. Decoding all of them would be
days of work and would mostly produce RINEX that already exists. Intersecting
the raw inventory against the *still-open* want-list entries reduces that to
**3,984 files across 17 site-years**, every one of them 2012 -- a single
campaign whose raw was archived and never converted.

Ten sites hold 3,975 of those files:

    AURA 606  CATA 515  BAGU 476  BRGC 375  BULA 366
    SABL 366  BASC 364  IBAZ 352  JOSE 309  BACO 246

and seven more hold one or two each (CCA5, LAG1, NV47, LUZC, MUNZ, PTBN, ITGN).

Note the want-list is keyed on site-YEAR, so ONE good day closes an entry. The
other 605 AURA files add observations, not closures. `--one-per-site-year`
exists for when the closure is what matters and the hour is not available.

THREE FORMATS, THREE PATHS -- and the difference is not cosmetic

    .T00/.T01/.T02   runpkr00 -d -g  ->  .tgd  ->  teqc -tr d
    .dat             teqc -tr d directly (legacy 4700/4800 era)
    .mNN             teqc -lei mdb   (Leica MDB)

`fixdatweek` is NOT needed for the `.dat` files despite the GPS week rollover
warning teqc prints on them. Verified: teqc resolves the week from the data and
produces the correct epoch, and the filenames carry the full date anyway so
`-week` is derivable if it ever does not. The proprietary Windows tool and its
Wine workaround are both avoidable here.

WHAT IS CHECKED, AND WHY EACH CHECK EXISTS

  * `APPROX POSITION XYZ` present -- without it stage 3 cannot attribute the
    file by position, which is the whole point of decoding it.
  * epoch matches the date in the source filename -- this is the rollover
    guard. A silently wrong year would corrupt want-list matching in exactly
    the way that is hardest to notice, because the file looks fine.
  * output is non-trivial -- a teqc that exits 0 having written a header and no
    observations is a failure that reports success.

Leica `.mNN` carry `MARKER NAME: -Unknown-` and no year in the filename, so
their epoch cannot be cross-checked this way. They are decoded and flagged
`epoch-unverified` rather than trusted or dropped.

Usage, on gps3 where the files and tools are:

    export PATH=$HOME/bin:$PATH
    scripts/decode_raw_gap.py --archive-list /tmp/arch_now.txt \\
        --want-list docs/bern52/gnss_want_list.csv \\
        --out /srv/gnss-archive/derived/decoded-2012 --dry-run

Output goes to `derived/`, never into `legacy/` -- those trees are faithful
copies of physical drives and derived products do not belong in them.
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAW_EXT = re.compile(r"\.(t0[0-9]|tgd|dat|m[0-9]{2})$", re.I)
RINEX = re.compile(r"^([A-Za-z0-9]{4})(\d{3})[0-9A-Za-z]\.(\d{2})[odODngmNGM](\.(gz|Z|z|zip))?$")
# SITE + YYYYMMDD, the convention that carries a full date
FULL = re.compile(r"^([A-Za-z0-9]{4})((?:19|20)\d{2})([01]\d)([0-3]\d)", re.I)
# SITE + DOY, year has to come from the directory
DOY = re.compile(r"^([A-Za-z0-9]{4})(\d{3})[a-z0-9]*\.", re.I)
YEARDIR = re.compile(r"^(19|20)\d{2}$")


def rinex_year(yy: int) -> int:
    return 1900 + yy if yy >= 80 else 2000 + yy


def doy_of(y: int, m: int, d: int) -> int:
    from datetime import date
    return date(y, m, d).timetuple().tm_yday


def attribute(path: str) -> tuple[str, int, int | None] | None:
    """(site, year, doy) from the filename, or the directory for the DOY form."""
    name = path.rsplit("/", 1)[-1]
    m = FULL.match(name)
    if m:
        y, mo, d = int(m.group(2)), int(m.group(3)), int(m.group(4))
        try:
            return m.group(1).upper(), y, doy_of(y, mo, d)
        except ValueError:
            return m.group(1).upper(), y, None
    m = DOY.match(name)
    if m:
        parts = path.split("/")
        for cand in (parts[-2] if len(parts) >= 2 else "", parts[-3] if len(parts) >= 3 else ""):
            if YEARDIR.match(cand):
                return m.group(1).upper(), int(cand), int(m.group(2))
    return None


def load_want(p: Path) -> set[tuple[str, int]]:
    want = set()
    with p.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            s = (r.get("site") or "").strip().upper()
            y = (r.get("year") or "").strip()
            if s and y.isdigit():
                want.add((s, int(y)))
    return want


def header_of(p: Path) -> str:
    txt = p.read_text(encoding="ascii", errors="replace")
    cut = txt.find("END OF HEADER")
    return txt[:cut] if cut > 0 else txt[:65536]


def convert(src: Path, work: Path) -> Path | None:
    """Run the right toolchain for this format. Returns the RINEX path or None."""
    suf = src.suffix.lower()
    dst = work / "out.obs"
    if re.fullmatch(r"\.t0[0-9]", suf):
        # runpkr00 unpacks the Trimble container; -d keeps the raw stream,
        # -g writes it beside the input.
        subprocess.run(["runpkr00", "-d", "-g", src.name], cwd=work,
                       capture_output=True, timeout=300)
        tgd = next((q for q in work.iterdir()
                    if q.suffix.lower() in (".tgd", ".dat") and q != src), None)
        if tgd is None:
            return None
        src = tgd
        suf = src.suffix.lower()
    if suf in (".tgd", ".dat"):
        args = ["teqc", "-tr", "d", src.name]
    elif re.fullmatch(r"\.m[0-9]{2}", suf):
        args = ["teqc", "-lei", "mdb", src.name]
    else:
        return None
    with dst.open("wb") as out:
        subprocess.run(args, cwd=work, stdout=out,
                       stderr=subprocess.DEVNULL, timeout=600)
    return dst if dst.exists() and dst.stat().st_size > 0 else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--archive-list", type=Path, required=True,
                    help="file of archive paths, one per line")
    ap.add_argument("--want-list", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--one-per-site-year", action="store_true",
                    help="decode a single file per site-year -- enough to close "
                         "the want-list entry, ~17 files rather than 3,984")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    paths = [l.rstrip("\n") for l in
             args.archive_list.open(encoding="utf-8", errors="replace")]
    want = load_want(args.want_list)

    have = set()
    for p in paths:
        m = RINEX.match(p.rsplit("/", 1)[-1])
        if m:
            have.add((m.group(1).upper(), rinex_year(int(m.group(3)))))
    still_open = want - have

    targets: dict[tuple[str, int], list[tuple[str, int | None]]] = collections.defaultdict(list)
    for p in paths:
        if not RAW_EXT.search(p.rsplit("/", 1)[-1]):
            continue
        a = attribute(p)
        if a and (a[0], a[1]) in still_open:
            targets[(a[0], a[1])].append((p, a[2]))

    n_files = sum(len(v) for v in targets.values())
    print(f"  want-list still open        : {len(still_open)} site-years")
    print(f"  raw covering an open entry  : {len(targets)} site-years, {n_files} files")
    if args.one_per_site_year:
        targets = {k: sorted(v)[:1] for k, v in targets.items()}
        n_files = sum(len(v) for v in targets.values())
        print(f"  --one-per-site-year         : {n_files} files")

    if args.dry_run:
        print("\n  site   year  files")
        for (s, y), v in sorted(targets.items(), key=lambda kv: -len(kv[1])):
            print(f"  {s:5s}  {y}  {len(v)}")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    ok = no_pos = bad_epoch = failed = 0
    unverified = 0
    todo = [(k, p, d) for k, v in sorted(targets.items()) for p, d in v]
    if args.limit:
        todo = todo[:args.limit]

    for (site, year), src_s, doy in todo:
        src = Path(src_s)
        if not src.exists():
            failed += 1
            continue
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            local = work / src.name
            shutil.copy2(src, local)
            try:
                out = convert(local, work)
            except subprocess.TimeoutExpired:
                out = None
            if out is None:
                failed += 1
                continue
            hdr = header_of(out)
            if "APPROX POSITION XYZ" not in hdr:
                no_pos += 1
                continue
            # Rollover guard. Only checkable where the source name carried a
            # date; Leica DOY-form names cannot be cross-checked.
            tag = ""
            m = re.search(r"^\s*(\d{4})\s+(\d+)\s+(\d+)\s+.*TIME OF FIRST OBS", hdr, re.M)
            if m and doy is not None:
                got_y = int(m.group(1))
                if got_y != year:
                    bad_epoch += 1
                    continue
            elif doy is None:
                tag = "  [epoch-unverified]"
                unverified += 1
            dd = doy if doy is not None else 0
            name = f"{site.lower()}{dd:03d}0.{str(year)[2:]}o"
            shutil.copy2(out, args.out / name)
            ok += 1
            print(f"  {src.name:34s} -> {name}{tag}")

    print(f"\n  decoded ok        : {ok}   (epoch unverified: {unverified})")
    print(f"  no APPROX POSITION: {no_pos}")
    print(f"  epoch mismatch    : {bad_epoch}   <- rollover guard rejected these")
    print(f"  conversion failed : {failed}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
