#!/usr/bin/env python3
"""Add a station to a Bernese campaign's reference files (readiness task A).

A station present in the RINEX but absent from the campaign's ``.STA`` makes
RXOBV3 **hard-abort** the whole cluster — the failure that killed DOY 086 during
the PAGENET training week. The workaround applied at the time was to move the
offending files into a hidden quarantine directory, which loses the station's
data permanently. This adds it properly instead.

WHY IT CLONES ROWS RATHER THAN FORMATTING THEM
----------------------------------------------
Bernese reference files are fixed-column. ``PGN.STA`` TYPE 002 rows are 272
characters across fourteen fields; a single column of drift silently shifts a
receiver serial into the antenna field, and Bernese will read the result without
complaint. So no format strings are written here. Instead an existing data row
is used as a template and only the known field ranges are overwritten, with the
ranges themselves derived from each file's own ``****`` ruler line where one
exists. Alignment is then correct by construction rather than by inspection.

WHAT CANNOT BE DERIVED FROM RINEX
---------------------------------
Velocity. A RINEX header carries position but no plate motion, so ``--apply``
seeds the velocity from the **nearest existing station** and labels it an
estimate. For PLG2 that is PSRG at 37.4 km, both on the Eurasian plate, where
the difference is well inside what CODSPP will absorb. It is still an a priori
value a geodesist should confirm.

DRY RUN BY DEFAULT. Nothing is written without ``--apply``; ``--apply`` backs up
every file it touches first.
"""
from __future__ import annotations

import argparse
import gzip
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REF_FILES = ("STA", "CRD", "VEL", "ABB", "CLU")


@dataclass
class StationMeta:
    """Everything derivable from a RINEX observation header."""

    name: str            # 4-char marker, e.g. PLG2
    dome: str            # DOMES number from MARKER NUMBER, e.g. 22015M002
    receiver: str        # REC # / TYPE / VERS, cols 20-39
    receiver_serial: str # REC # / TYPE / VERS, cols 0-19
    antenna: str         # ANT # / TYPE, cols 20-39
    antenna_serial: str  # ANT # / TYPE, cols 0-19
    x: float
    y: float
    z: float

    @property
    def full_name(self) -> str:
        """`NAME DOMES` as it appears in the STATION NAME column."""
        return f"{self.name} {self.dome}"


def _open_text(path: Path):
    """Read a RINEX file, plain or compressed. Mirrors the validator's handling.

    A CRINEX (Hatanaka) file stores the original header verbatim after two
    CRINEX lines, so no crx2rnx is needed to read what we want here.
    """
    s = path.suffix.lower()
    if s == ".gz":
        return gzip.open(path, "rt", encoding="ascii", errors="replace")
    if s == ".z":
        # Python has no LZW decoder; GNU gzip reads both formats.
        return subprocess.Popen(
            ["gzip", "-dc", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="ascii", errors="replace",
        ).stdout
    return path.open(encoding="ascii", errors="replace")


def read_station_meta(rinex: Path) -> StationMeta:
    """Extract station metadata from a RINEX observation header."""
    fields: dict[str, str] = {}
    fh = _open_text(rinex)
    try:
        for raw in fh:
            line = raw.rstrip("\n")
            if len(line) < 61:
                continue
            label = line[60:].strip()
            if label in (
                "MARKER NAME", "MARKER NUMBER",
                "REC # / TYPE / VERS", "ANT # / TYPE", "APPROX POSITION XYZ",
            ):
                fields[label] = line[:60]
            elif label == "END OF HEADER":
                break
    finally:
        try:
            fh.close()
        except Exception:  # noqa: BLE001 - closing a cut-off pipe can SIGPIPE
            pass

    missing = [k for k in ("MARKER NAME", "REC # / TYPE / VERS", "ANT # / TYPE",
                          "APPROX POSITION XYZ") if k not in fields]
    if missing:
        raise ValueError(f"{rinex.name}: header missing {missing}")

    xyz = fields["APPROX POSITION XYZ"].split()
    return StationMeta(
        name=fields["MARKER NAME"].strip()[:4].upper(),
        dome=fields.get("MARKER NUMBER", "").strip() or "00000M000",
        receiver=fields["REC # / TYPE / VERS"][20:40].strip(),
        receiver_serial=fields["REC # / TYPE / VERS"][:20].strip(),
        antenna=fields["ANT # / TYPE"][20:40].strip(),
        antenna_serial=fields["ANT # / TYPE"][:20].strip(),
        x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2]),
    )


# --- row cloning ------------------------------------------------------------


def _overwrite(row: str, start: int, width: int, value: str) -> str:
    """Replace a fixed-width field, left-justified, without shifting anything."""
    row = row.ljust(start + width)
    return row[:start] + value.ljust(width)[:width] + row[start + width:]


def ruler_fields(lines: list[str], start_at: int = 0) -> list[tuple[int, int]]:
    """(start, width) of each field, read from the file's own ``****`` ruler.

    These files document their own column layout in a line of asterisk runs
    directly under the column headings. Reading it beats hardcoding offsets,
    which is not a hypothetical preference: the first version of this script
    hardcoded the ABB 2-ID at column 33 when the ruler says 34, so the
    uniqueness check compared `' C'` against real 2-IDs, matched nothing it
    should have, and emitted a three-character ID into a two-character field.
    The docstring already claimed offsets came from the ruler. They now do.
    """
    for ln in lines[start_at:]:
        if ln.startswith("****"):
            return [(m.start(), len(m.group())) for m in re.finditer(r"\*+", ln)]
    raise ValueError("no '****' ruler line found")


def _data_rows(lines: list[str], pattern: re.Pattern) -> list[tuple[int, str]]:
    return [(i, ln) for i, ln in enumerate(lines) if pattern.match(ln)]


_CRD_ROW = re.compile(r"^\s*\d+\s+[A-Z0-9]{4}\s")
_ABB_ROW = re.compile(r"^[A-Z0-9]{4}\s")
_CLU_ROW = re.compile(r"^[A-Z0-9]{4}\s")
_STA_ROW = re.compile(r"^[A-Z0-9]{4}\s.*\s001\s")


def nearest_station(crd_text: str, meta: StationMeta) -> tuple[str, float]:
    """Nearest existing station by 3-D distance, for the velocity a priori."""
    best: list[tuple[float, str]] = []
    for line in crd_text.splitlines():
        m = re.match(
            r"\s*\d+\s+([A-Z0-9]{4})\s+\S*\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)",
            line,
        )
        if not m:
            continue
        d = math.dist(
            (meta.x, meta.y, meta.z),
            (float(m.group(2)), float(m.group(3)), float(m.group(4))),
        )
        best.append((d / 1000.0, m.group(1)))
    if not best:
        raise ValueError("no stations found in CRD to seed velocity from")
    d, name = min(best)
    return name, d


def build_crd_row(lines: list[str], meta: StationMeta) -> tuple[int, str]:
    rows = _data_rows(lines, _CRD_ROW)
    idx, template = rows[-1]
    num = max(int(re.match(r"\s*(\d+)", ln).group(1)) for _, ln in rows) + 1
    row = template
    row = _overwrite(row, 0, 3, f"{num:>3}")
    row = _overwrite(row, 5, 16, meta.full_name)
    row = _overwrite(row, 21, 15, f"{meta.x:15.5f}")
    row = _overwrite(row, 36, 15, f"{meta.y:15.5f}")
    row = _overwrite(row, 51, 15, f"{meta.z:15.5f}")
    return idx + 1, row.rstrip()


def build_vel_row(
    lines: list[str], meta: StationMeta, donor: str
) -> tuple[int, str]:
    rows = _data_rows(lines, _CRD_ROW)
    donor_rows = [ln for _, ln in rows if f" {donor} " in ln]
    if not donor_rows:
        raise ValueError(f"donor station {donor} not present in VEL")
    idx = rows[-1][0]
    num = max(int(re.match(r"\s*(\d+)", ln).group(1)) for _, ln in rows) + 1
    row = donor_rows[0]                      # keep the donor's velocity values
    row = _overwrite(row, 0, 3, f"{num:>3}")
    row = _overwrite(row, 5, 16, meta.full_name)
    return idx + 1, row.rstrip()


def build_abb_row(lines: list[str], meta: StationMeta) -> tuple[int, str]:
    (n_at, n_w), (id4_at, id4_w), (id2_at, id2_w), (rem_at, rem_w) = ruler_fields(lines)
    rows = _data_rows(lines, _ABB_ROW)
    idx, template = rows[-1]

    used2 = {ln[id2_at:id2_at + id2_w].strip() for _, ln in rows}
    two = meta.name[:2]
    if two in used2:                          # the 2-ID must be unique
        for c in "23456789ABCDEFGHJKLMNPQRSTUVWXYZ":
            if (cand := meta.name[0] + c) not in used2:
                two = cand
                break
        else:
            raise ValueError(f"no free 2-ID for {meta.name}")

    row = _overwrite(template, n_at, n_w, meta.full_name)
    row = _overwrite(row, id4_at, id4_w, meta.name)
    row = _overwrite(row, id2_at, id2_w, two)
    row = _overwrite(row, rem_at, rem_w, "Added for intermittent station")
    return idx + 1, row.rstrip()


def build_clu_row(lines: list[str], meta: StationMeta) -> tuple[int, str]:
    (n_at, n_w), *_ = ruler_fields(lines)
    rows = _data_rows(lines, _CLU_ROW)
    idx, template = rows[-1]
    # Cluster number is inherited from the template. Every PAGENET station is
    # currently in cluster 1 — the single-cluster final solve behind the 40-min
    # 502 GPSCLU_P bottleneck. Splitting clusters is readiness task P2-K and is
    # deliberately not done here.
    row = _overwrite(template, n_at, n_w, meta.full_name)
    return idx + 1, row.rstrip()


def build_sta_rows(text: str, meta: StationMeta) -> list[tuple[str, int, str]]:
    """TYPE 001 (renaming) and TYPE 002 (station information) rows."""
    lines = text.splitlines()
    out: list[tuple[str, int, str]] = []

    bounds = {}
    for tag in ("TYPE 001", "TYPE 002", "TYPE 003"):
        for i, ln in enumerate(lines):
            if ln.startswith(tag):
                bounds[tag] = i
                break
    if "TYPE 001" not in bounds or "TYPE 002" not in bounds:
        raise ValueError("STA file has no TYPE 001/002 blocks")
    end002 = bounds.get("TYPE 003", len(lines))

    # TYPE 001 — clone the last renaming row.
    b1 = [(i, ln) for i, ln in enumerate(lines[bounds["TYPE 001"]:bounds["TYPE 002"]],
                                         start=bounds["TYPE 001"])
          if _STA_ROW.match(ln)]
    idx, tmpl = b1[-1]
    f1 = ruler_fields(lines, bounds["TYPE 001"])
    (n_at, n_w) = f1[0]
    (old_at, old_w) = f1[2]
    (rem_at, rem_w) = f1[3]
    row = _overwrite(tmpl, n_at, n_w, meta.full_name)
    row = _overwrite(row, old_at, old_w, f"{meta.name}*")
    row = _overwrite(row, rem_at, rem_w, "Added: was quarantined")
    out.append(("TYPE 001", idx + 1, row.rstrip()))

    # TYPE 002 — clone the last information row, then set the metadata fields.
    b2 = [(i, ln) for i, ln in enumerate(lines[bounds["TYPE 002"]:end002],
                                         start=bounds["TYPE 002"])
          if _STA_ROW.match(ln)]
    idx, tmpl = b2[-1]
    f2 = ruler_fields(lines, bounds["TYPE 002"])
    row = _overwrite(tmpl, *f2[0], meta.full_name)          # STATION NAME
    row = _overwrite(row, *f2[2], meta.receiver)            # RECEIVER TYPE
    row = _overwrite(row, *f2[3], meta.receiver_serial)     # RECEIVER SERIAL
    row = _overwrite(row, *f2[5], meta.antenna)             # ANTENNA TYPE
    row = _overwrite(row, *f2[6], meta.antenna_serial)      # ANTENNA SERIAL
    row = _overwrite(row, *f2[-1], "Added: was quarantined")  # REMARK
    out.append(("TYPE 002", idx + 1, row.rstrip()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Add a station to a Bernese campaign's reference files.",
        epilog="Dry run by default; --apply backs up every file it writes.",
    )
    ap.add_argument("--rinex", type=Path, required=True,
                    help="a RINEX observation file for the station")
    ap.add_argument("--ref-dir", type=Path,
                    default=Path("/home/gps3/GPSDATA/DATAPOOL/REF54"))
    ap.add_argument("--prefix", default="PGN", help="reference file prefix")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not args.rinex.exists():
        print(f"FATAL: no such RINEX file: {args.rinex}", file=sys.stderr)
        return 1

    meta = read_station_meta(args.rinex)
    print(f"Station derived from {args.rinex.name}:")
    for k, v in (
        ("name", meta.name), ("DOMES", meta.dome),
        ("receiver", f"{meta.receiver}  (s/n {meta.receiver_serial})"),
        ("antenna", f"{meta.antenna}  (s/n {meta.antenna_serial})"),
        ("X Y Z", f"{meta.x:.4f}  {meta.y:.4f}  {meta.z:.4f}"),
    ):
        print(f"  {k:9s}: {v}")

    files = {ext: args.ref_dir / f"{args.prefix}.{ext}" for ext in REF_FILES}
    for path in files.values():
        if not path.is_file():
            print(f"FATAL: missing {path}", file=sys.stderr)
            return 1

    crd_text = files["CRD"].read_text(encoding="ascii", errors="replace")
    present = [e for e, p in files.items()
               if meta.name in p.read_text(encoding="ascii", errors="replace")]
    if present:
        print(f"\n{meta.name} is ALREADY present in: {', '.join(present)} — nothing to do.")
        return 0

    donor, dist = nearest_station(crd_text, meta)
    print(f"\nVelocity a priori: cloned from {donor} ({dist:.1f} km away)")
    print("  NOT derivable from RINEX — have a geodesist confirm this.\n")

    planned: dict[str, list[tuple[int, str]]] = {}
    sta_text = files["STA"].read_text(encoding="ascii", errors="replace")
    planned["STA"] = [(i, r) for _, i, r in build_sta_rows(sta_text, meta)]
    for ext, builder in (
        ("CRD", lambda ls: [build_crd_row(ls, meta)]),
        ("VEL", lambda ls: [build_vel_row(ls, meta, donor)]),
        ("ABB", lambda ls: [build_abb_row(ls, meta)]),
        ("CLU", lambda ls: [build_clu_row(ls, meta)]),
    ):
        lines = files[ext].read_text(encoding="ascii", errors="replace").splitlines()
        planned[ext] = builder(lines)

    print("Rows to insert:")
    for ext in REF_FILES:
        for _, row in planned[ext]:
            print(f"  {args.prefix}.{ext:3s} | {row[:118]}")

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for ext in REF_FILES:
        path = files[ext]
        shutil.copy2(path, path.with_suffix(f".{ext}.bak-{stamp}"))
        lines = path.read_text(encoding="ascii", errors="replace").splitlines()
        for offset, (idx, row) in enumerate(sorted(planned[ext])):
            lines.insert(idx + offset, row)
        path.write_text("\n".join(lines) + "\n", encoding="ascii")
        print(f"  wrote {path.name}  (backup .bak-{stamp})")

    print(f"\n{meta.name} added. Re-run the validator to confirm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
