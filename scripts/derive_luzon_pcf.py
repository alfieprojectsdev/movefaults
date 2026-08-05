#!/usr/bin/env python3
"""Derive a LUZON PCF from Bernese 5.4's stock RNX2SNX.PCF.

WHY FROM RNX2SNX AND NOT FROM THE 5.2 PCF
`PHIVOL_REL.PCF` is PHIVOLCS' 5.2 variant of the same RNX2SNX workflow, so
adapting it looked like the faithful route. It is not adaptable: **the PCF file
format changed between 5.2 and 5.4.**

    5.2  PID SCRIPT   OPT_DIR  CAMPAIGN CPU      F WAIT FOR....
         3** 8******* 8******* 8******* 8******* 1 3** 3** ...
         501 GPSCLUAP R2S_FIN           ANY      1 499

    5.4  501  GPSCLUAP  R2S_FIN   CPU=ANY; WAIT=499;  PARAM2=V_FIN

Fixed-column with a ruler line, versus free-form `KEY=VALUE;`. Handing 5.4 a 5.2
PCF produces a **segmentation fault in the menu program**, not a parse error, so
the incompatibility is not self-announcing. Renaming scripts and repairing WAIT
lists — which is what the first attempt did — cannot bridge a format change.

`PAGENET_DLY.PCF` is 5.4-native and proven, but it needs the `PGN_*` OPT
directories, which exist only on the T420. Stock `RNX2SNX.PCF` needs `R2S_*`,
which ship with 5.4. Hence this.

WHAT IT CHANGES: only variables. The process graph, script names and OPT
directories are 5.4's own and are left exactly as installed.

    V_PCV     I20        -> I14        antenna model; see runbook §1.4
    V_REFINF  IGS20      -> IGS14      reference frame
    V_REFPSD  IGS20      -> IGS14
    V_CRDINF  EXAMPLE    -> LUZON      merged CRD/VEL
    V_STAINF  EXAMPLE    -> LUZON      station information
    V_BLQINF  EXAMPLE    -> LUZON      ocean loading
    V_ATLINF  (blank)    -> LUZON      atmospheric loading
    V_RNXDIR  ${D}/RINEX -> ${D}/LUZON RINEX 2 observations
    V_GNSSAR  GRE        -> ALL        all *selected* systems get AR
    V_SATSYS  GRE        -> GPS        she processed GPS only -- see the note
                                       in OVERRIDES; this is why I14 works
    V_MYATX   (blank)    -> I14.ATX    ATX2PCV updates the PCV model, as hers did
    V_CLU     8          -> 10         her cluster size
    V_DEL     Y          -> N          keep results in the campaign to inspect
    V_SAVOBS  Y          -> N          ditto

V_ORB and V_ORBDIR are LEFT AT COD0OPSFIN, the 5.4 default. An earlier revision
pointed them at IGS0OPSFIN because IGS products are anonymously available from
BKG. That fails: `R2S_COP` derives the satellite-bias filename from `V_ORB`, and
**only CODE publishes the bias**. Orbits, clocks, ERP and biases must come from
one analysis centre or the names do not line up — which is why 5.4 ships
defaulting to CODE, and why the working EXAMPLE campaign uses that set.

The 5.2 set ships orbits in legacy naming (`igs22364.sp3.Z`); 5.4 reads
long-name. The products were "already local" and simultaneously unusable, which
is why the runbook's claim that FTP_DWLD could be dropped was wrong. Fetch with
scripts/fetch_igs_products.sh before running.

DELIBERATELY NOT CHANGED: baselines (V_BL_*), which already match her values,
and the process graph. Every difference from her run should be one we chose.
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

OVERRIDES = {
    "V_PCV": "I14",
    "V_REFINF": "IGS14",
    "V_REFPSD": "IGS14",
    "V_CRDINF": "LUZON",
    "V_STAINF": "LUZON",
    "V_BLQINF": "LUZON",
    "V_ATLINF": "LUZON",
    "V_RNXDIR": "${D}/LUZON",
    "V_GNSSAR": "ALL",
    # THE ONE THAT MATTERS MOST. V_SATSYS selects which constellations are
    # PROCESSED; V_GNSSAR only says which of those get ambiguity resolution.
    # 5.4 ships V_SATSYS=GRE (GPS+GLONASS+Galileo); her 5.2 PCF has GPS.
    #
    # Copying V_GNSSAR=ALL while leaving V_SATSYS at the 5.4 default made the
    # run attempt GLONASS, and CODSPP then died on GLONASS-M 861 -- a satellite
    # launched after the I14 model's epoch and absent from every I14 table,
    # hers and 5.4's alike (both stop at 860; only I20 has 861).
    #
    # So this is not a workaround for a missing file. Processing GPS only is
    # what she did, and it is *why* I14 remains valid against 2025 data.
    "V_SATSYS": "GPS",
    # V_MYATX IS DELIBERATELY LEFT BLANK, though her run logs
    # "Antenna phase center model updated with: I14.ATX".
    #
    # Setting it makes ATX2PCV (PID 002) merge the ANTEX into the phase-centre
    # file. On 5.4 that FAILS for every I14 ANTEX in her tree:
    #
    #   *** PG ATX2PCV: Given SVN and PRN inconsistent in ANTEX file.
    #                   PRN: 22   SVN: G041
    #
    # I14.ATX carries four G041 entries (different PRN mappings across epochs);
    # I14-orig.ATX and I14_1.ATX carry one each and fail the same check. 5.4
    # validates SVN-to-PRN consistency that 5.2 did not, so a file her run
    # consumed without complaint is rejected outright.
    #
    # Leaving it blank gets to PID 232 (CODSPP); setting it stops at PID 002.
    # Neither reaches a solution -- see runbook §4b.6 -- but the blank form
    # fails later and more informatively.
    "V_CLU": "10",
    "V_DEL": "N",
    "V_SAVOBS": "N",
}


def apply_overrides(text: str) -> tuple[str, list[str]]:
    changed: list[str] = []
    out = []
    for line in text.splitlines():
        m = re.match(r"^(V_\w+)(\s*=\s*)([^;]*)(;.*)$", line)
        if m and m.group(1) in OVERRIDES:
            name, sep, old, tail = m.groups()
            new = OVERRIDES[name]
            if old.strip() != new:
                changed.append(f"{name}: {old.strip() or '(blank)'} -> {new}")
                line = f"{name}{sep}{new}{tail}"
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    U = Path(os.environ.get("U", Path.home() / "GPSUSER"))
    ap.add_argument("--src", type=Path, default=U / "PCF" / "RNX2SNX.PCF")
    ap.add_argument("--dest", type=Path, default=U / "PCF" / "LUZON_DLY.PCF")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not args.src.is_file():
        print(f"FATAL: {args.src} not found", file=sys.stderr)
        return 1

    text, changed = apply_overrides(args.src.read_text(errors="replace"))

    print(f"src : {args.src}\ndest: {args.dest}\n")
    print("variable overrides applied:")
    for c in changed:
        print(f"  {c}")

    missing = sorted(set(OVERRIDES) - {c.split(":")[0] for c in changed})
    if missing:
        print("\nalready at target value (or not present):")
        for m in missing:
            print(f"  {m}")

    dangling = find_dangling_waits(text)
    print(f"\ndangling WAITs: {len(dangling)}")
    if dangling:
        for d in dangling[:6]:
            print(f"  L{d.line} WAIT={d.pid}")
        print("REFUSING — a WAIT on an undefined PID hangs the BPE forever.")
        return 1

    # Guard the format: 5.4 rows carry `CPU=`. A file without them is the 5.2
    # dialect, which segfaults the menu program rather than failing cleanly.
    rows = re.findall(r"^\d{3}\s+\S+.*$", text, re.M)
    keyword_rows = [r for r in rows if "CPU=" in r]
    print(f"process rows: {len(rows)}, of which 5.4-keyword style: {len(keyword_rows)}")
    if rows and len(keyword_rows) != len(rows):
        print("REFUSING — not a 5.4-format PCF (rows without CPU=).")
        return 1

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply.")
        return 0

    args.dest.write_text(text, encoding="ascii")
    print(f"\nwrote {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
