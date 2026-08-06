#!/usr/bin/env python3
"""Merge ocean-loading (BLQ) station blocks into an existing Bernese BLQ file.

WHY THIS IS NEEDED
`LUZON.BLQ` covers the 135 local PHIVOLCS stations and none of the IGS
fiducials. With the fiducials staged, `GPSEDT` stops:

    *** SR GTOCNL: OCEAN LOADING CORRECTION VALUES NOT FOUND
                   STATION NAME : ALIC 50137M001
                   FILE NAME    : ${P}/LUZON/STA/LUZON.BLQ

No `.BLQ` anywhere in the 5.2 capture contains ALIC, so this is not a staging
mistake — the coefficients were never computed for those sites. They come from
the Chalmers/Onsala OTL service, which delivers by **email**, so acquiring them
is a manual step. This handles everything on either side of that step.

WHY IT DOES NOT JUST APPEND
Bernese matches BLQ stations by name, and a duplicate block is worse than a
missing one: which of two conflicting entries wins is not obvious from the file.
This refuses to add a station that is already present unless `--replace` is
given, and reports rather than guessing.

Usage:
    scripts/merge_blq.py --blq <target.BLQ> --new <onsala-reply.txt>
    scripts/merge_blq.py --blq ... --new ... --apply
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# A station block header in Scherneck/Onsala BLQ output: two leading spaces then
# the site name, e.g. "  ALIC". Comment lines start with $$ and are not blocks.
_STATION_RE = re.compile(r"^\s{2}(\S+)\s*$")


def parse_blocks(text: str) -> dict[str, list[str]]:
    """Split BLQ text into {station: [lines]} — the block plus its $$ comments.

    A block runs from its name line until the next name line, so leading $$
    comment lines that belong to a station travel with it.
    """
    lines = text.splitlines()
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    buf: list[str] = []
    pending: list[str] = []

    for ln in lines:
        m = _STATION_RE.match(ln)
        if m and not ln.strip().startswith("$$"):
            if current:
                blocks[current] = buf
            current = m.group(1).upper()
            buf = pending + [ln]
            pending = []
        elif current is None and ln.strip().startswith("$$"):
            pending.append(ln)          # file header, kept out of any block
        elif current is not None:
            if ln.strip().startswith("$$") and _looks_like_header(ln):
                pending.append(ln)      # header for the NEXT station
            else:
                buf.append(ln)
    if current:
        blocks[current] = buf
    return blocks


def _looks_like_header(line: str) -> bool:
    """True for the $$ banner lines Onsala emits before each station block."""
    low = line.lower()
    return any(k in low for k in ("column order", "ocean loading", "scherneck", "olfg"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--blq", type=Path, required=True, help="target BLQ to merge into")
    ap.add_argument("--new", type=Path, required=True, help="Onsala reply containing new blocks")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--replace", action="store_true", help="overwrite stations already present")
    args = ap.parse_args()

    for f in (args.blq, args.new):
        if not f.is_file():
            print(f"FATAL: not found: {f}", file=sys.stderr)
            return 1

    target_text = args.blq.read_text(encoding="ascii", errors="replace")
    existing = parse_blocks(target_text)
    incoming = parse_blocks(args.new.read_text(encoding="ascii", errors="replace"))

    print(f"target   : {args.blq}  ({len(existing)} stations)")
    print(f"incoming : {args.new}  ({len(incoming)} stations)\n")

    if not incoming:
        print("No station blocks parsed from the reply. Check that it is the raw")
        print("BLQ text and not an HTML page or a quoted-printable email body.")
        return 1

    to_add, clash = [], []
    for name in incoming:
        (clash if name in existing else to_add).append(name)

    if to_add:
        print(f"will add ({len(to_add)}): {' '.join(sorted(to_add))}")
    if clash:
        verb = "will REPLACE" if args.replace else "already present, SKIPPING"
        print(f"{verb} ({len(clash)}): {' '.join(sorted(clash))}")
        if not args.replace:
            print("  (pass --replace to overwrite them)")

    # Sanity-check each incoming block: 6 numeric rows, 11 columns each.
    bad = []
    for name in to_add + (clash if args.replace else []):
        rows = [ln for ln in incoming[name]
                if ln.strip() and not ln.strip().startswith("$$")
                and not _STATION_RE.match(ln)]
        numeric = [r for r in rows if len(r.split()) == 11]
        if len(numeric) != 6:
            bad.append(f"{name}: {len(numeric)} rows of 11 values (expected 6)")
    if bad:
        print("\nMALFORMED BLOCKS — refusing:")
        for b in bad:
            print(f"  {b}")
        print("\nBernese needs 3 amplitude rows then 3 phase rows, 11 values each.")
        return 1
    print("\nall incoming blocks have 6 rows x 11 values")

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = args.blq.with_suffix(f".BLQ.bak-{stamp}")
    shutil.copy2(args.blq, backup)

    out = target_text.rstrip("\n") + "\n"
    for name in to_add:
        out += "\n".join(incoming[name]).rstrip("\n") + "\n"
    if args.replace:
        for name in clash:
            old = "\n".join(existing[name])
            out = out.replace(old, "\n".join(incoming[name]))

    args.blq.write_text(out, encoding="ascii")
    merged = parse_blocks(args.blq.read_text(encoding="ascii", errors="replace"))
    print(f"\nwrote {args.blq}  ({len(existing)} -> {len(merged)} stations)")
    print(f"backup: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
