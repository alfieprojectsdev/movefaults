#!/usr/bin/env python3
"""Check that every station in a list is readable in a Bernese reference set.

WHY THIS EXISTS
Bernese reports a missing reference entry as NOT FOUND, never as malformed,
and three different defects produce that same message with the station
plainly visible in the file (docs/SETTLED.md §2):

  * a BLQ block indented one column left           (*** SR GTOCNL)
  * a BLQ block placed after `$$ END TABLE`        (*** SR GTOCNL)
  * an ATL header that is not the .CRD station name (*** SR GTATML)

Each was found by a failed BPE run, minutes or hours in. A `grep "\\bCODE\\b"`
presence check passes all three -- it once passed on a comment line. This
reads the files the way Bernese does, so the failure surfaces before the run.

WHAT IT CHECKS, per station code
  CRD  the code has a coordinate line; its 16-character name is the key
       every other file is checked against
  STA  a line starts with that full name
  ABB  a line starts with that full name
  BLQ  a block header `  CODE` exists ABOVE `$$ END TABLE`, in column 3
  ATL  a header line equals the full name exactly

What it does NOT check: whether the values are right. MILA's a priori in
PHNAT.CRD is 97 m off and passes here, correctly -- that is a different
question (see the PHDEN DOY 199 finding). And for BLQ it checks only the
layout that is known to work; whether a full-name BLQ header is also
accepted is untested, so it is not asserted either way.

WHICH FILES
--pcf is the safer mode. A campaign gets its reference files through its PCF
variables, not its name: PHREF_DLY reads PHNAT.*, so `--set PHREF` would check
the wrong files. --pcf resolves them as $U/SCRIPT/R2S_COP does -- CRD and ABB
from V_CRDINF, STA from V_STAINF, BLQ/ATL from their own variables, and BLQ or
ATL not checked when the variable is empty, because R2S_COP does not copy them.

Usage:
    scripts/check_ref_coverage.py --pcf PHDEN_DLY --stations ~/phivolcs-weekly/WK_2375.sites.txt
    scripts/check_ref_coverage.py --set PHDEN --stations ~/phivolcs-weekly/WK_2375.sites.txt
    scripts/check_ref_coverage.py --set PHNAT --stations list.txt --ref-dir $D/REF54

Exit status: 0 when every station is readable in every file, 1 otherwise,
2 when a file is missing.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

KINDS = ("CRD", "STA", "ABB", "BLQ", "ATL")

# The readers live in the bernese-workflow service, which runs the same checks
# inside a run plan; one copy, so the two cannot come to read a file differently.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "bernese-workflow" / "src"))

from bernese_workflow.station_files import (  # noqa: E402
    _lines,
    atl_status,
    blq_status,
    crd_names,
    name_listed,
)

__all__ = ["atl_status", "blq_status", "check", "crd_names", "name_listed", "pcf_sets"]


def check(codes: list[str], files: dict[str, str]) -> list[tuple[str, str, str]]:
    """(code, file kind, problem) for every station not readable in a file."""
    names = crd_names(files["CRD"])
    problems = []
    for code in codes:
        candidates = names.get(code, [])
        if len(candidates) > 1:
            # Bernese reaches the name through the STA renaming, so the STA
            # file is what decides which of the CRD's names this station is
            candidates = [n for n in candidates if name_listed(files["STA"], n)] or candidates
        if not candidates:
            problems.append((code, "CRD", "absent"))
            continue
        if len(candidates) > 1:
            listed = ", ".join(f"'{n}'" for n in candidates)
            problems.append((code, "CRD", f"ambiguous: {listed} all in CRD and STA"))
            continue
        full = candidates[0]
        for kind in ("STA", "ABB"):
            if not name_listed(files[kind], full):
                problems.append((code, kind, "absent"))
        if files["BLQ"] is not None:
            status = blq_status(files["BLQ"], code)
            if status != "ok":
                problems.append((code, "BLQ", status))
        if files["ATL"] is not None:
            status = atl_status(files["ATL"], full)
            if status != "ok":
                problems.append((code, "ATL", status))
    return problems


# Which PCF variable names each file. Mirrors $U/SCRIPT/R2S_COP, which copies
# ${crdInf}.CRD, ${crdInf}.ABB, ${staInf}.STA, and ${blqInf}.BLQ / ${atlInf}.ATL
# only when those variables are non-empty. ABB follows CRDINF, not STAINF.
_PCF_VAR = {
    "CRD": "V_CRDINF",
    "ABB": "V_CRDINF",
    "STA": "V_STAINF",
    "BLQ": "V_BLQINF",
    "ATL": "V_ATLINF",
}


def pcf_sets(text: str) -> dict[str, str]:
    """File kind -> reference set name the PCF resolves it to ('' = not used)."""
    values = {}
    for line in _lines(text):
        m = re.match(r"^(V_\w+)\s*=\s*([^;]*);", line)
        if m:
            values[m[1]] = m[2].strip()
    return {kind: values[var] for kind, var in _PCF_VAR.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--set", help="reference set name for all five files, e.g. PHDEN")
    which.add_argument(
        "--pcf",
        help="PCF name, e.g. PHREF_DLY: check the files that PCF actually resolves to "
        "(PHREF_DLY reads PHNAT.*, which --set PHREF would miss)",
    )
    ap.add_argument("--stations", type=Path, required=True, help="one 4-char code per line")
    default_ref = Path(os.environ.get("D", str(Path.home() / "GPSDATA/DATAPOOL"))) / "REF54"
    ap.add_argument("--ref-dir", type=Path, default=default_ref)
    default_pcf = Path(os.environ.get("U", str(Path.home() / "GPSUSER"))) / "PCF"
    ap.add_argument("--pcf-dir", type=Path, default=default_pcf)
    args = ap.parse_args()

    if args.pcf:
        pcf = args.pcf_dir / f"{args.pcf}.PCF"
        if not pcf.is_file():
            print(f"missing: {pcf}", file=sys.stderr)
            return 2
        try:
            sets = pcf_sets(pcf.read_text(encoding="latin-1"))
        except KeyError as e:
            print(f"{pcf}: no {e.args[0]} variable", file=sys.stderr)
            return 2
        for kind in ("CRD", "ABB", "STA"):
            if not sets[kind]:
                # R2S_COP copies these unconditionally; only BLQ/ATL may be blank
                print(f"{pcf}: {_PCF_VAR[kind]} is empty", file=sys.stderr)
                return 2
        label = args.pcf
    else:
        sets = dict.fromkeys(KINDS, args.set)
        label = args.set

    files: dict[str, str | None] = {}
    for kind in KINDS:
        if not sets[kind]:
            files[kind] = None  # the PCF does not use this file; Bernese skips it too
            continue
        path = args.ref_dir / f"{sets[kind]}.{kind}"
        if not path.is_file():
            print(f"missing: {path}", file=sys.stderr)
            return 2
        files[kind] = path.read_text(encoding="latin-1")

    try:
        station_text = args.stations.read_text()
    except OSError as e:
        print(f"cannot read station list: {e}", file=sys.stderr)
        return 2
    codes = [c.strip().upper() for c in station_text.split() if c.strip()]
    problems = check(codes, files)
    used = [f"{sets[k]}.{k}" for k in KINDS if files[k] is not None]
    print(f"{label}: {len(codes)} stations against {', '.join(used)}: {len(problems)} problem(s)")
    for code, kind, what in problems:
        print(f"  {code}  {sets[kind]}.{kind:<3}  {what}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
