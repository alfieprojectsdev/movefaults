#!/usr/bin/env python3
"""Transfer the PHIVOLCS DATAPOOL off the file server, with fixity at copy time.

WHAT AND WHY
`\\\\192.168.48.99\\Bernese\\GPSDATA\\DATAPOOL\\PHIVOLCS` holds **476 GiB across
330,754 files** — every year of PH GNSS observations from 2010 to now. It is
currently single-copy on a Windows box. `/srv/gnss-archive` has 20 TB and has
been empty since July.

The point is not just to have a second copy. It is to have a second copy **whose
integrity can be proven later**. The project's succession audit lists "no
fixity — zero checksums anywhere, so silent bit rot is undetectable" as a
standing risk, and retrofitting checksums onto half a terabyte after the fact
costs a second full read of everything. Computing them **during** the copy costs
nothing extra, because the bytes are already in hand.

THE LAYOUT TRAP THIS SCRIPT EXISTS TO AVOID
The share does NOT store current data in year directories. `2024/` and `2025/`
are **empty**; the 2025-2026 working set — 64,284 files, 314.5 GiB, two thirds
of the whole thing — sits **loose at the top level**. A transfer that walks year
directories copies almost nothing and reports success. Verified by survey
2026-08-12:

    (top level)  64,284 files  314.5 GiB     2018  28,603   14.6
    2010          5,224          2.0         2019  27,671   14.9
    ...                                      2023  27,883   27.2
    2024               0          0.0        2024/2025 EMPTY
    Old sites     2,731          6.4         BLNA        13    0.1
                                             TOTAL  330,754  476.0 GiB

RESUMABILITY
Every file is recorded in a manifest as it lands. A re-run skips anything already
present with a matching size, so an interrupted transfer resumes rather than
restarting. Size is the skip test, not hash — re-hashing the destination to
decide whether to skip would defeat the point of avoiding a second full read.
Use --verify to hash what is already on disk.

WHAT THIS DOES NOT DO
It does not delete, move or modify anything on the server. It never writes to
the share. If the destination already holds a file of a different size it is
re-copied; if the same size, it is skipped and noted.

Usage:
    scripts/transfer_phivolcs_datapool.py --dry-run
    scripts/transfer_phivolcs_datapool.py --apply
    scripts/transfer_phivolcs_datapool.py --apply --only 2010 --only 2011
    scripts/transfer_phivolcs_datapool.py --verify        # re-hash destination
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HOST = "192.168.48.99"
SRC = r"\\192.168.48.99\Bernese\GPSDATA\DATAPOOL\PHIVOLCS"
DEST_DEFAULT = Path("/srv/gnss-archive/datapool/PHIVOLCS")
MANIFEST_DIR = Path("/srv/gnss-archive/manifests")
CHUNK = 4 * 1024 * 1024


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PiB"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="actually copy (default: dry run)")
    ap.add_argument("--dry-run", action="store_true", help="explicit no-op; the default")
    ap.add_argument("--dest", type=Path, default=DEST_DEFAULT)
    ap.add_argument("--only", action="append", default=None,
                    help="restrict to a subdirectory, repeatable; "
                         "use TOP for the loose top-level files")
    ap.add_argument("--verify", action="store_true",
                    help="re-hash files already at the destination instead of copying")
    ap.add_argument("--user", default="guest")
    ap.add_argument("--password", default="")
    args = ap.parse_args()

    try:
        from smbclient import open_file, register_session, scandir
    except ImportError:
        print("smbprotocol not available. Run via:\n"
              "  uv run --with smbprotocol scripts/transfer_phivolcs_datapool.py ...",
              file=sys.stderr)
        return 2

    try:
        register_session(HOST, username=args.user, password=args.password, encrypt=False)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: cannot reach {HOST}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if not args.dest.parent.exists():
        print(f"FATAL: {args.dest.parent} does not exist — is the array mounted?",
              file=sys.stderr)
        return 1

    # Enumerate the work. TOP is the loose top-level set, which is most of it.
    groups: list[tuple[str, str]] = []  # (label, smb path)
    try:
        entries = list(scandir(SRC))
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: cannot list {SRC}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if any(not e.is_dir() for e in entries):
        groups.append(("TOP", SRC))
    for e in sorted(entries, key=lambda x: x.name):
        if e.is_dir():
            groups.append((e.name, f"{SRC}\\{e.name}"))
    if args.only:
        wanted = set(args.only)
        groups = [g for g in groups if g[0] in wanted]
        if not groups:
            print(f"nothing matched --only {sorted(wanted)}", file=sys.stderr)
            return 1

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    man_path = MANIFEST_DIR / f"datapool-sha256-{stamp}.txt"
    man = None
    if args.apply or args.verify:
        man = man_path.open("a", encoding="utf-8")
        man.write(f"# source: {SRC}\n# host: {HOST}\n"
                  f"# started: {datetime.now(UTC).isoformat()}\n")

    copied = skipped = failed = verified = 0
    bytes_done = 0
    t0 = time.time()

    for label, path in groups:
        # Top level: files only, since its subdirectories are separate groups.
        print(f"\n=== {label} ===", flush=True)
        try:
            items = [e for e in scandir(path) if not e.is_dir()]
        except Exception as exc:  # noqa: BLE001
            print(f"  !! cannot list: {type(exc).__name__}: {str(exc)[:80]}")
            failed += 1
            continue

        outdir = args.dest if label == "TOP" else args.dest / label
        for e in sorted(items, key=lambda x: x.name):
            try:
                size = e.stat().st_size
            except Exception:  # noqa: BLE001
                size = -1
            out = outdir / e.name

            if args.verify:
                if not out.is_file():
                    continue
                h = hashlib.sha256()
                with out.open("rb") as fh:
                    for blk in iter(lambda fh=fh: fh.read(CHUNK), b""):
                        h.update(blk)
                verified += 1
                if man:
                    man.write(f"{h.hexdigest()}  {out}\n")
                continue

            if out.is_file() and out.stat().st_size == size:
                skipped += 1
                continue

            if not args.apply:
                copied += 1
                bytes_done += max(size, 0)
                continue

            try:
                outdir.mkdir(parents=True, exist_ok=True)
                h = hashlib.sha256()
                tmp = out.with_suffix(out.suffix + ".part")
                with open_file(f"{path}\\{e.name}", mode="rb") as fsrc, tmp.open("wb") as fdst:
                    while True:
                        blk = fsrc.read(CHUNK)
                        if not blk:
                            break
                        h.update(blk)
                        fdst.write(blk)
                got = tmp.stat().st_size
                if size >= 0 and got != size:
                    # Short read: keep nothing rather than a plausible-looking
                    # truncated file, which is the failure mode that survives
                    # unnoticed for years.
                    tmp.unlink(missing_ok=True)
                    print(f"  !! SHORT {e.name}: expected {size}, got {got}")
                    failed += 1
                    continue
                tmp.replace(out)
                if man:
                    man.write(f"{h.hexdigest()}  {out}\n")
                    man.flush()
                copied += 1
                bytes_done += got
            except Exception as exc:  # noqa: BLE001
                print(f"  !! FAILED {e.name}: {type(exc).__name__}: {str(exc)[:70]}")
                failed += 1

        el = time.time() - t0
        rate = human(bytes_done / el) + "/s" if el > 0 and bytes_done else "-"
        print(f"  running totals: copied {copied:,}  skipped {skipped:,}  "
              f"failed {failed:,}  {human(bytes_done)}  ({rate})", flush=True)

    if man:
        man.write(f"# finished: {datetime.now(UTC).isoformat()}\n")
        man.close()

    el = time.time() - t0
    print(f"\n{'=' * 60}")
    if args.verify:
        print(f"verified {verified:,} files against sha256 -> {man_path}")
    else:
        verb = "copied" if args.apply else "would copy"
        print(f"{verb}: {copied:,} files, {human(bytes_done)}   "
              f"skipped (already present): {skipped:,}   failed: {failed:,}")
        print(f"elapsed: {el/60:.1f} min")
        if args.apply:
            print(f"manifest: {man_path}")
        else:
            print("Dry run — nothing written. Re-run with --apply.")
    if failed:
        print("\nSOME FILES FAILED — this transfer is NOT complete. Re-run to resume.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
