#!/usr/bin/env python3
"""Derive a Bernese 5.4 LUZON PCF from the PHIVOLCS 5.2 production PCF.

Reproduces `$U/PCF/LUZON_DLY.PCF` from
`config/bernese/gpsuser52-luzon/PCF/PHIVOL_REL.PCF`, so the adaptation is a
reviewable transformation rather than a hand-edited file nobody can re-derive.
Runbook: docs/bernese54_luzon_reprocessing_runbook.md §4.1.

WHAT IT CHANGES, AND WHY EACH

Dropped PIDs
  000 FTP_DWLD  every product for the window is already staged (§1.1c)
  112 PRETAB    5.4 has no PRETAB in any form. 5.2 chained
                ORBMRG(111) -> PRETAB(112) -> ORBGENH(113); 5.4's own stock
                RNX2SNX chains ORBMRG(111) -> ORBGEN(112). So PRETAB is
                REMOVED and ORBGEN waits on 101+111 directly. It is NOT
                "substituted with ORBMRG" — ORBMRG already exists at 111, and
                substituting would have created a duplicate.
  530 ADD_WK    weekly combination, out of scope for a daily comparison, and
  531 ADD_MON   monthly ditto. Dropping these is also what frees us from
                provisioning PHI_WK/PHI_MO — they are referenced nowhere else.
  902 R2S_SAV   archive to SAVEDISK, and
  903 R2S_DEL   wipe the campaign. Kept OUT deliberately for a first run: this
                pair is exactly why the DOY 121-151 solutions looked missing on
                2026-08-04. For a smoke test, leaving results in the campaign
                where they can be inspected is worth more than archiving them.
  991 BPE_CLN   removes BPE working directories; keep them for debugging.

Renamed scripts (the _H/H suffix is on the SCRIPT only — OPT panels are named
without it, so panel lookups are unaffected)
  POLUPDH  -> POLUPD      ORBGENH  -> ORBGEN
  RXOBV3_H -> RXOBV3      RNXSMT_H -> RNXSMT_P

Repaired WAIT lists, forced by the drops
  001 -> (none)          was waiting on the dropped 000
  113 -> 101 111         was waiting on the dropped 112
  599 -> 512 513 514 522 was also waiting on the dropped 530 531
  999 -> 901             was waiting on the dropped 991

Variable changes
  V_PCVINF PCV -> ANTENNA   {V_PCVINF}_{V_PCV} must resolve to a file that
                            exists. 5.2 wanted PCV_I14.PCV; 5.4 ships
                            ANTENNA_I14.PCV. Leaving this at PCV makes Bernese
                            look for a filename absent from the 5.4 tree.
  V_REFDIR REF52 -> REF54   the 5.4 reference directory.

Deliberately UNCHANGED: V_PCV=I14, V_REFINF=IGS14, V_GNSSAR=ALL. Those define
the comparison. Changing them to the 5.4 PAGENET defaults (I20/IGS20/GRE) is
the confound the whole exercise exists to avoid — see runbook §1.4.

Verify the result with panel_sanitizer.find_dangling_waits(): a WAIT on a PID
that no longer exists does not fail loudly, it makes the BPE wait forever.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "bernese-workflow" / "src"))

from bernese_workflow.panel_sanitizer import find_dangling_waits  # noqa: E402

DROP = {
    "000": "FTP_DWLD — products already staged",
    "112": "PRETAB — absent from 5.4; ORBMRG(111) feeds ORBGEN directly",
    "530": "ADD_WK — weekly combine, out of scope",
    "531": "ADD_MON — monthly combine, out of scope",
    "902": "R2S_SAV — keep results in the campaign for inspection",
    "903": "R2S_DEL — do not wipe the campaign",
    "991": "BPE_CLN — keep BPE logs for debugging",
}
RENAME = {
    "POLUPDH": "POLUPD",
    "ORBGENH": "ORBGEN",
    "RXOBV3_H": "RXOBV3",
    "RNXSMT_H": "RNXSMT_P",
}
REWAIT = {"001": "", "113": "101 111", "599": "512 513 514 522", "999": "901"}


def adapt(text: str) -> tuple[str, list[str], list[str]]:
    lines = text.splitlines()
    end = next(i for i, ln in enumerate(lines) if ln.startswith("PID USER"))
    out: list[str] = []
    dropped: list[str] = []
    renamed: list[str] = []

    for i, line in enumerate(lines):
        m = re.match(r"^(\d{3}) (\S+)(\s+.*)$", line) if i < end else None
        if not m:
            out.append(line)
            continue
        pid, script, rest = m.groups()
        if pid in DROP:
            dropped.append(f"{pid} {script:<9} {DROP[pid]}")
            continue
        if script in RENAME:
            renamed.append(f"{pid} {script} -> {RENAME[script]}")
            script = RENAME[script]
        if pid in REWAIT:
            head = re.match(r"^(\s+\S+\s+\S+\s+\S+\s+\S+)", rest).group(1)
            rest = head + ("  " + REWAIT[pid] if REWAIT[pid] else "")
        out.append(f"{pid} {script:<8}{rest}")

    result = "\n".join(out) + "\n"
    result = re.sub(r"^(V_PCVINF\s+\S.*?)\bPCV\s*$", r"\1ANTENNA", result, flags=re.M)
    result = re.sub(r"^(V_REFDIR\s+\S.*?)\bREF52\b", r"\1REF54", result, flags=re.M)
    return result, dropped, renamed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--src",
        type=Path,
        default=REPO_ROOT / "config/bernese/gpsuser52-luzon/PCF/PHIVOL_REL.PCF",
    )
    ap.add_argument(
        "--dest",
        type=Path,
        default=Path(os.environ.get("U", Path.home() / "GPSUSER")) / "PCF" / "LUZON_DLY.PCF",
    )
    ap.add_argument("--apply", action="store_true", help="write it (default: dry run)")
    args = ap.parse_args()

    if not args.src.is_file():
        print(f"FATAL: source PCF not found: {args.src}", file=sys.stderr)
        return 1

    text, dropped, renamed = adapt(args.src.read_text(errors="replace"))

    print(f"src : {args.src}")
    print(f"dest: {args.dest}\n")
    print("dropped PIDs:")
    for d in dropped:
        print(f"  {d}")
    print("\nrenamed scripts:")
    for r in renamed:
        print(f"  {r}")

    dangling = find_dangling_waits(text)
    print(f"\ndangling WAITs in the result: {len(dangling)}")
    for d in dangling[:8]:
        print(f"  L{d.line} WAIT={d.pid}")
    if dangling:
        print("\nREFUSING: a WAIT on an undefined PID makes the BPE hang forever.")
        return 1

    n_pids = len(re.findall(r"^\d{3} ", text, re.M))
    print(f"PIDs in the result: {n_pids}")

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply.")
        return 0

    args.dest.parent.mkdir(parents=True, exist_ok=True)
    args.dest.write_text(text, encoding="ascii")
    print(f"\nwrote {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
