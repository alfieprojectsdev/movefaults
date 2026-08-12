#!/usr/bin/env python3
"""Snapshot PHIVOLCS' production scripts and event catalog off the file server.

WHY THIS EXISTS
The scripts that actually run the MOVE Faults workflow -- and the hand-curated
`offsets` event catalog behind every velocity estimate -- live only on
\\\\192.168.48.99 (a Windows box, hostname WIN-8I2S1803RV5) and on staff
machines. They are not in version control anywhere. The `offsets` file in
particular is years of accumulated institutional judgement about which
coordinate jumps were earthquakes, eruptions, equipment changes, or unknown --
it cannot be regenerated from anything.

This copies the small text artifacts into the repo so they survive a disk
failure, a staff departure, or a reorganised share. It is READ-ONLY against
the server.

WHAT IT DELIBERATELY SKIPS
Installers and binaries: UltraEdit.zip (103 MB), the Octave installer
(318 MB), teqc.exe / runpkr00.exe / convertToRinex314.msi, .exe/.msi/.zip
generally. Those are redistributable third-party tools, not project knowledge,
and they would bloat the repo for no succession benefit. The DEFAULT size cap
is deliberately low for the same reason.

NAMES DIFFER FROM THE WORK INSTRUCTION
Cass noted the SOP renamed scripts for readability, since the document goes
through PHIVOLCS peer review and into the library archives. Confirmed:
`filter-fncrd.bat` is really `00_CRD_PIVS.bat` (and per-network variants),
`plot_v2.py` is really a 01_GETXYZ -> 02_TRANSFORM -> 03_GETENU ->
04_PLOTFILES pipeline driven by RUN.py/RUNX_v*.py, and `vel_line_v8.m` is
`vel_line.m`. Snapshot the real names; map them in the docs.

Usage:
    scripts/snapshot_phivolcs_scripts.py --dry-run
    scripts/snapshot_phivolcs_scripts.py --apply
    scripts/snapshot_phivolcs_scripts.py --apply --max-bytes 500000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HOST = "192.168.48.99"
DEST_DEFAULT = Path(__file__).resolve().parent.parent / "docs" / "bern52" / "phivolcs-scripts"

# (server path, destination subdirectory, recurse depth)
SOURCES = [
    (r"\\192.168.48.99\GPS Data\Scripts\For Bernese 5.2", "for-bernese-5.2", 2),
    (r"\\192.168.48.99\GPS Data\Scripts\RINEX conversion", "rinex-conversion", 2),
    (r"\\192.168.48.99\GPS Data\Scripts\RINEX Checker", "rinex-checker", 1),
    (r"\\192.168.48.99\GPS Data\Scripts\S01R - Hatanaka to RINEX", "s01r-hatanaka", 1),
    (r"\\192.168.48.99\GPS Data\Scripts\To modify IGS (RINEXV3)", "modify-igs-rinex3", 1),
    (
        r"\\192.168.48.99\GPS Data\TIME SERIES (BERN52)\Campaign"
        r"\FINAL PLOT FILES (complete, with discontinuities)",
        "event-catalog",
        1,
    ),
]

# Text-ish artifacts worth preserving. Everything else is skipped.
KEEP_SUFFIXES = {".py", ".m", ".bat", ".txt", ".md", ".csv", ".inp", ".pcf", ".sh", ".pl"}
# Extensionless files worth keeping by exact (lowercased) name.
KEEP_NAMES = {"offsets", "123", "readme"}
SKIP_NAMES = {"thumbs.db", "desktop.ini"}


def want(name: str, size: int, max_bytes: int) -> tuple[bool, str]:
    low = name.lower()
    if low in SKIP_NAMES:
        return False, "noise"
    if size > max_bytes:
        return False, f"too big ({size:,} B)"
    suffix = Path(low).suffix
    if suffix in KEEP_SUFFIXES:
        return True, ""
    if not suffix and low in KEEP_NAMES:
        return True, ""
    return False, f"not a text artifact ({suffix or 'no suffix'})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write files (default: dry run)")
    ap.add_argument("--dry-run", action="store_true", help="explicit no-op, the default")
    ap.add_argument("--dest", type=Path, default=DEST_DEFAULT)
    ap.add_argument("--max-bytes", type=int, default=1_000_000,
                    help="skip anything larger (default 1 MB) -- keeps installers out")
    ap.add_argument("--user", default="guest")
    ap.add_argument("--password", default="")
    args = ap.parse_args()

    try:
        from smbclient import open_file, register_session, scandir
    except ImportError:
        print("smbprotocol not available. Run via:\n"
              "  uv run --with smbprotocol scripts/snapshot_phivolcs_scripts.py ...",
              file=sys.stderr)
        return 2

    try:
        register_session(HOST, username=args.user, password=args.password, encrypt=False)
    except Exception as exc:  # noqa: BLE001 - report and stop, do not guess credentials
        print(f"FATAL: cannot authenticate to {HOST}: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1

    copied = skipped = failed = 0
    total_bytes = 0

    def walk(src: str, dest: Path, depth: int, maxd: int) -> None:
        nonlocal copied, skipped, failed, total_bytes
        try:
            entries = sorted(scandir(src), key=lambda e: e.name)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! cannot list {src}: {type(exc).__name__}")
            failed += 1
            return
        for e in entries:
            if e.is_dir():
                if depth < maxd:
                    walk(f"{src}\\{e.name}", dest / e.name, depth + 1, maxd)
                continue
            try:
                size = e.stat().st_size
            except Exception:  # noqa: BLE001
                size = -1
            ok, why = want(e.name, size, args.max_bytes)
            if not ok:
                skipped += 1
                continue
            out = dest / e.name
            print(f"  {'COPY' if args.apply else 'would copy'}  {out.relative_to(args.dest)}"
                  f"  ({size:,} B)")
            if not args.apply:
                copied += 1
                total_bytes += max(size, 0)
                continue
            try:
                with open_file(f"{src}\\{e.name}", mode="rb") as fh:
                    data = fh.read()
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
                copied += 1
                total_bytes += len(data)
            except Exception as exc:  # noqa: BLE001
                print(f"     !! failed: {type(exc).__name__}: {str(exc)[:80]}")
                failed += 1

    for src, sub, maxd in SOURCES:
        print(f"\n=== {src}")
        walk(src, args.dest / sub, 0, maxd)

    print(f"\n{'copied' if args.apply else 'would copy'}: {copied} files, "
          f"{total_bytes:,} B   skipped: {skipped}   failed: {failed}")
    if not args.apply:
        print("Dry run - nothing written. Re-run with --apply.")
    if failed:
        print("SOME FILES FAILED - do not treat this snapshot as complete.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
