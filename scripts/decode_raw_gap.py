#!/usr/bin/env python3
"""Decode the raw receiver files that would close an open want-list site-year.

WHY ONLY SOME OF THEM
`RAW_EXT` over `/srv/gnss-archive` on gps3 matches **80,954** files:
46,061 `.t02`, 17,654 `.m00`, 7,683 `.t00`, 4,526 `.t01`, 2,372 `.dat` and the
rest spread thinly across `.mNN`. Decoding all of them would be days of work
and would mostly produce RINEX that already exists.

`.tgd` is in `RAW_EXT` and its count in that archive is **zero**. That is
correct rather than an oversight: `.tgd` is the runpkr00 intermediate this
script produces itself, in a temp dir, on the way from `.T0x` to teqc. It is
matched so a stray intermediate left by an earlier run is picked up rather
than skipped, not because the archive stores any. Intersecting
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

`fixdatweek` is NOT needed for the `.dat` files in THIS corpus, and the scope
of that claim matters. Every `.dat` reachable from the open want-list entries
is from 2012 -- 781 of them -- so they sit between the 1999-08-21 and
2019-04-06 rollovers and cross neither. On those files teqc resolved the week
from the data and the epoch guard below confirmed the result against the date
in the filename, file by file.

That is evidence about 781 files on one side of one boundary. It is NOT a
general property of teqc across rollovers, and it should not be quoted as one.
What makes it safe to rely on here is not teqc's behaviour but the guard: if
teqc ever does resolve a week wrongly, the epoch cross-check rejects the file
rather than filing it under the wrong year. The filenames also carry the full
date, so `-week` is derivable if it is ever needed. The proprietary Windows
tool and its Wine workaround are avoidable for this run.

EVERY INPUT LEAVES THROUGH EXACTLY ONE COUNTER

The first run of this script reported 3,869 decoded ok and left 2,977 files on
disk. Nothing raised an error; the 892 were only visible to someone who counted
the directory afterwards. The cause was the RINEX 2 session character,
hardcoded `0` -- so every source for one site-day wrote to the same path and
kept the last -- made much worse by Leica `.mNN` names carrying no DOY at all,
which sent an entire site-year to `site0000.YYo`.

Two things changed and the second matters more than the first. `allocate()`
uses the session field for what it is for, so a site-day with several sources
keeps all of them. And the run now RECONCILES: every input leaves through
exactly one counter, the ok count is compared against the directory, and a
mismatch is printed to stderr. A summary that cannot be checked against the
filesystem is how the first 892 stayed invisible.

Every file also gets a row in `decode_manifest.csv` -- outcome and, on failure,
the tool's own stderr. The first run recorded 113 conversion failures as a
number with no causes attached, which made them uninvestigable without redoing
the whole run.

NOTE ON `.dat`, WHICH TWO SCRIPTS DISAGREE ABOUT

`RAW_EXT` here includes `.dat`. `want_list_diff.py`'s `_RAW` does not, and that
disagreement is silent: it is the entire reason a decode of 16 site-years
closed 4 want-list entries. The twelve others were already counted as covered
by their `.t0x`/`.mNN` raw, and the four that closed were precisely the ones
whose raw is `.dat`. One definition should import the other.

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
import os
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


TOOLS = {
    "runpkr00": "unpacks Trimble .T0x containers",
    "teqc": "converts .dat/.tgd/.mNN to RINEX",
}


def require_tools(names: list[str]) -> str | None:
    """Return an error string naming what is missing, or None if all are present.

    `shutil.which` and not a bare `subprocess.run`, because a missing binary
    surfaces as `FileNotFoundError` with only the program name in it, and this
    project has already lost time to the opposite confusion -- `command -v`
    reporting these absent while they were installed but off PATH. On gps3 all
    three live in `/home/gps3/bin`, which is not on a non-login shell's PATH,
    so the failure is a PATH problem far more often than a missing install.
    """
    missing = [n for n in names if shutil.which(n) is None]
    if not missing:
        return None
    lines = [f"missing on PATH: {', '.join(missing)}"]
    for n in missing:
        lines.append(f"    {n:<10} {TOOLS.get(n, '')}")
    lines.append("")
    lines.append("  These are not distribution packages. If they are installed,")
    lines.append("  PATH is the likely cause -- on gps3 they live in $HOME/bin:")
    lines.append("      export PATH=$HOME/bin:$PATH")
    lines.append(f"  PATH is currently: {os.environ.get('PATH', '(unset)')}")
    return "\n".join(lines)


def allocate(out: Path, site: str, year: int, doy: int,
             hour: int | None) -> tuple[str | None, str]:
    """Pick a RINEX 2 short name for this site-day that is not already taken.

    The session field is the 8th character. `0` means a daily file; `a`-`x` are
    the 24 hourly sessions. An earlier version hardcoded `0`, so a site-day with
    more than one source file wrote every one of them to the same path and kept
    only the last -- 892 of 3,869 decoded files, 23%, lost with no error raised
    and a summary reporting them all as ok.

    Preference order, so the common case is unchanged and the format still
    means what it says:

      1. `0` -- daily, and what a single-file site-day still gets
      2. the hour letter from TIME OF FIRST OBS, which is what the field is FOR
      3. any free letter, for sources that collide within the same hour

    Returns `(name, why)`; `why` is empty when nothing had to be disambiguated,
    and names the reason when it did. `(None, why)` means all 25 were taken,
    which needs a person rather than a 26th fallback.
    """
    yy = str(year)[2:]
    stem = f"{site.lower()}{doy:03d}"

    plain = f"{stem}0.{yy}o"
    if not (out / plain).exists():
        return plain, ""

    if hour is not None and 0 <= hour < 24:
        c = chr(ord("a") + hour)
        cand = f"{stem}{c}.{yy}o"
        if not (out / cand).exists():
            return cand, f"session {c} from hour {hour:02d}"

    for c in "abcdefghijklmnopqrstuvwx":
        cand = f"{stem}{c}.{yy}o"
        if not (out / cand).exists():
            return cand, f"session {c}, hour ambiguous"

    return None, f"all 25 sessions taken for {stem}"


def convert(src: Path, work: Path) -> tuple[Path | None, str]:
    """Run the right toolchain for this format.

    Returns `(rinex_path, reason)`. On failure the path is None and the reason
    is the tool's own stderr, trimmed. An earlier version returned bare None
    and sent stderr to DEVNULL, which made 113 failures in a 3,984-file run
    uninvestigable without repeating the whole run -- the count was recorded
    and the cause was thrown away.
    """
    suf = src.suffix.lower()
    dst = work / "out.obs"
    if re.fullmatch(r"\.t0[0-9]", suf):
        # runpkr00 unpacks the Trimble container; -d keeps the raw stream,
        # -g writes it beside the input.
        r = subprocess.run(["runpkr00", "-d", "-g", src.name], cwd=work,
                           capture_output=True, timeout=300)
        tgd = next((q for q in work.iterdir()
                    if q.suffix.lower() in (".tgd", ".dat") and q != src), None)
        if tgd is None:
            return None, _trim(r.stderr) or f"runpkr00 wrote no .tgd (rc={r.returncode})"
        src = tgd
        suf = src.suffix.lower()
    if suf in (".tgd", ".dat"):
        args = ["teqc", "-tr", "d", src.name]
    elif re.fullmatch(r"\.m[0-9]{2}", suf):
        args = ["teqc", "-lei", "mdb", src.name]
    else:
        return None, f"no toolchain for {suf}"
    with dst.open("wb") as out:
        r = subprocess.run(args, cwd=work, stdout=out,
                           stderr=subprocess.PIPE, timeout=600)
    if not dst.exists() or dst.stat().st_size == 0:
        return None, _trim(r.stderr) or f"teqc produced no output (rc={r.returncode})"
    return dst, ""


def _trim(b: bytes, n: int = 200) -> str:
    """First meaningful stderr line, collapsed to one line and capped."""
    txt = b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b)
    for ln in txt.splitlines():
        ln = ln.strip()
        if ln:
            return ln[:n]
    return ""


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

    paths = [ln.rstrip("\n") for ln in
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

    # Preflight, and only for what this selection actually needs -- a run with
    # no .T0x in it has no business demanding runpkr00. Checked here rather
    # than in `convert`, so a missing tool costs one line instead of one
    # failure per file, and after --dry-run, which needs neither tool.
    needed = ["teqc"]
    if any(re.search(r"\.t0[0-9]$", pth, re.I)
           for v in targets.values() for pth, _ in v):
        needed.insert(0, "runpkr00")
    err = require_tools(needed)
    if err:
        print(f"FATAL: {err}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    ok = no_pos = bad_epoch = failed = 0
    unverified = disambiguated = collided = undated = doy_from_header = 0
    rows: list[tuple] = []
    todo = [(k, p, d) for k, v in sorted(targets.items()) for p, d in v]
    if args.limit:
        todo = todo[:args.limit]

    for (site, year), src_s, doy in todo:
        src = Path(src_s)
        if not src.exists():
            failed += 1
            rows.append((src_s, site, year, "", "missing", "not on disk"))
            continue
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            local = work / src.name
            shutil.copy2(src, local)
            try:
                out, why = convert(local, work)
            except subprocess.TimeoutExpired:
                out, why = None, "timed out"
            if out is None:
                failed += 1
                rows.append((src_s, site, year, "", "convert-failed", why))
                continue
            hdr = header_of(out)
            if "APPROX POSITION XYZ" not in hdr:
                no_pos += 1
                rows.append((src_s, site, year, "", "no-APPROX-POSITION", ""))
                continue
            # Rollover guard. Only checkable where the source name carried a
            # date; Leica DOY-form names cannot be cross-checked.
            tag = ""
            m = re.search(r"^\s*(\d{4})\s+(\d+)\s+(\d+)\s+(\d+)"
                          r".*TIME OF FIRST OBS", hdr, re.M)
            if m and doy is not None:
                got_y = int(m.group(1))
                if got_y != year:
                    bad_epoch += 1
                    rows.append((src_s, site, year, "",
                                 "epoch-mismatch", f"header year {got_y}"))
                    continue
            elif doy is None:
                tag = "  [epoch-unverified]"
                unverified += 1

            # The DOY, and where it comes from. Leica .mNN names carry none, so
            # an earlier version fell back to 0 -- which meant EVERY Leica file
            # for a site-year landed on `site0000.YYo` and overwrote the last.
            # The header has the date whenever teqc could read one, so use it.
            dd, hour = doy, None
            if m:
                hour = int(m.group(4))
                if dd is None:
                    dd = doy_of(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    doy_from_header += 1

            if dd is None:
                undated += 1
                rows.append((src_s, site, year, "", "no-date",
                             "filename carries no DOY and teqc wrote no "
                             "TIME OF FIRST OBS"))
                continue

            name, why = allocate(args.out, site, year, dd, hour)
            if name is None:
                collided += 1
                rows.append((src_s, site, year, "", "name-exhausted", why))
                continue
            if why:
                disambiguated += 1
                tag += f"  [{why}]"
            shutil.copy2(out, args.out / name)
            ok += 1
            rows.append((src_s, site, year, name, "ok", why))
            print(f"  {src.name:34s} -> {name}{tag}")

    manifest = args.out / "decode_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "site", "year", "output", "outcome", "detail"])
        w.writerows(rows)

    print(f"\n  decoded ok        : {ok}   (epoch unverified: {unverified})")
    if doy_from_header:
        print(f"    DOY from header : {doy_from_header}   <- source name carried none")
    if disambiguated:
        print(f"    disambiguated   : {disambiguated}   <- would have overwritten")
    print(f"  no APPROX POSITION: {no_pos}")
    print(f"  epoch mismatch    : {bad_epoch}   <- rollover guard rejected these")
    print(f"  no usable date    : {undated}")
    print(f"  name exhausted    : {collided}")
    print(f"  conversion failed : {failed}")

    # The check that would have caught the 892. Every input must leave through
    # exactly one of the counters above, and every ok must be a file on disk.
    seen = ok + no_pos + bad_epoch + undated + collided + failed
    on_disk = len([q for q in args.out.iterdir()
                   if q.is_file() and q.name != manifest.name])
    print(f"\n  accounted for     : {seen} of {len(todo)}")
    print(f"  files on disk     : {on_disk}   (expected {ok})")
    if seen != len(todo) or on_disk != ok:
        print("  !! MISMATCH -- inputs or outputs are unaccounted for",
              file=sys.stderr)
    print(f"  manifest          : {manifest}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
