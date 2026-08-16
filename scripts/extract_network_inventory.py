#!/usr/bin/env python3
"""
Turn the PHIVOLCS site-inventory spreadsheet into two reviewable CSVs.

Source
------
Google Sheets, "Inventory / Site MetaData" working sheet:
    https://docs.google.com/spreadsheets/d/1Y8TTzfMwAfqlkYcbyfs_m0cv2ovEZcbObTDvx7EFxVA
exported as Markdown tables. Pass the export path as the only argument.

Why an intermediate CSV rather than seeding straight from the sheet
-------------------------------------------------------------------
The sheet is a live working document — columns are added, rows are re-sorted,
and (see below) at least one column no longer holds what its header says. A
committed CSV makes the seed reproducible, reviewable in a diff, and runnable
without network access or Drive credentials. Re-run this script when the sheet
changes; the diff then shows exactly what moved.

Three tables are read out of the export
---------------------------------------
1. **Site metadata** — the only block with coordinates. Covers ABUY..ORMO
   (87 rows); the sheet's own numbering stops there, so the remaining sites
   have no coordinates anywhere in the document.
2. **Equipment** — 117 rows, one per site, receiver/antenna/power/comms.
3. **Site names** — 131 rows of `SITE CODE | LOCATION | PERIOD | METHOD`,
   the widest coverage of any block and the source of the human-readable name.

The union is 131 sites, of which 87 have coordinates and 117 have equipment.

Columns that do not contain what their header claims
----------------------------------------------------
`antenna_cable_length` holds prose describing which floor the receiver sits on
("The floor below the rooftop of a 2 storey building") — 0 of 117 values parse
as a number. `other_equipment` holds the receiver's position relative to the
antenna ("within the same building"). Both are preserved as free text in
`housing_notes`; neither is written to `cable_length_m`, which stays NULL
rather than being populated with a fabricated number.

`satellite_systems`, `firmware_version` and `elevation_cutoff` are empty for
every row. The last two matter beyond tidiness: elevation cutoff and ARP height
are Bernese .STA inputs, and this sheet cannot supply them.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "network_inventory"

# Row offsets of each block's first data row in the Markdown export, with the
# row count. Positional because the export has no stable anchors — verified
# against the header row directly above each block (see _check_header).
SITES_START, SITES_N = 12, 87
EQUIP_START, EQUIP_N = 103, 117
NAMES_START, NAMES_N = 812, 131

# A fourth block, five side-by-side lists wide, built for an
# epicentre-distance calculation rather than as an inventory. Its first list
# and its NAMRIA list are the only place in the document where several Palawan
# sites carry coordinates, so they are read — but marked, because a site that
# appears only in an analysis scratch block has no verified status, no
# installation date, and in the NAMRIA case a different owner entirely.
ANALYSIS_START, ANALYSIS_N = 755, 53
ANALYSIS_HEADER_FIRST = ("SITE", "LOCATION", "LAT")
NAMRIA_COL = 17  # the first of the three `NAMRIA Site | Location | Lat | Long` lists

SITES_HEADER_FIRST = ("TEMP_IFVERIFIED", "i", "site_code")
EQUIP_HEADER_FIRST = ("i", "site_code", "date_installed")
NAMES_HEADER_FIRST = ("SITE CODE", "LOCATION", "PERIOD CONSTRUCTED")

_MONTHS = {
    m: f"{i:02d}"
    for i, m in enumerate(
        "january february march april may june july august "
        "september october november december".split(),
        start=1,
    )
}


def cells(line: str) -> list[str]:
    """Split one Markdown table row, stripping the export's backslash escapes."""
    return [c.strip().replace("\\", "") for c in line.strip().strip("|").split("|")]


def _check_header(lines: list[str], start: int, expected: tuple[str, ...]) -> None:
    """
    Fail loudly if a block is not where we expect it.

    The offsets above are positional, so a re-sorted or extended sheet would
    otherwise be silently mis-parsed into plausible-looking rows — the worst
    outcome for a seed file nobody reads line by line.
    """
    header = cells(lines[start - 1])
    if tuple(header[: len(expected)]) != expected:
        raise SystemExit(
            f"Block at line {start} does not start with {expected!r}.\n"
            f"Found: {header[:len(expected)]!r}\n"
            "The sheet layout has changed — update the offsets in this script "
            "rather than trusting the output."
        )


def norm_date(raw: str) -> str:
    """
    Normalise the four date spellings the sheet uses, or return "".

    Year-only and "2013 (?)" values are deliberately dropped rather than
    widened to 1 January: a fabricated day that looks precise is worse than a
    missing one, and these feed equipment valid-time intervals.
    """
    v = (raw or "").strip()
    if not v:
        return ""
    if m := re.match(r"^(\d{2})/(\d{2})/(\d{4})$", v):          # 09/28/2017
        mm, dd, yyyy = m.groups()
        return f"{yyyy}-{mm}-{dd}"
    if m := re.match(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$", v):  # Jan 07, 2026
        mon = _MONTHS.get(m.group(1).lower()[:3] and _full_month(m.group(1)))
        if mon:
            return f"{m.group(3)}-{mon}-{int(m.group(2)):02d}"
    return ""


def _full_month(prefix: str) -> str:
    p = prefix.lower()
    for name in _MONTHS:
        if name.startswith(p):
            return name
    return ""


def norm_float(raw: str) -> str:
    v = (raw or "").strip()
    return v if re.match(r"^-?\d+(\.\d+)?$", v) else ""


def norm_int(raw: str) -> str:
    """'555 Channels' -> '555'."""
    m = re.match(r"^(\d+)", (raw or "").strip())
    return m.group(1) if m else ""


def yes_no(raw: str) -> str:
    v = (raw or "").strip().lower()
    return "true" if v == "yes" else "false" if v == "no" else ""


def has_lightning(raw: str) -> str:
    v = (raw or "").strip().lower()
    if "arrester" in v or "arrestor" in v:
        return "true"
    if v in {"n/a", "no", "none"}:
        return "false"
    return ""


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} <sheet-export.json|.md>")

    src = Path(sys.argv[1])
    text = src.read_text(encoding="utf-8")
    # Sniff the content rather than the extension — the Drive export arrives as
    # JSON with a .txt name, and keying off the suffix silently parsed the raw
    # JSON as Markdown and produced an empty document.
    if text.lstrip().startswith("{"):
        text = json.loads(text)["fileContent"]
    lines = text.split("\n")

    _check_header(lines, SITES_START, SITES_HEADER_FIRST)
    _check_header(lines, EQUIP_START, EQUIP_HEADER_FIRST)
    _check_header(lines, NAMES_START, NAMES_HEADER_FIRST)

    meta = {
        r[2]: r
        for r in (cells(x) for x in lines[SITES_START : SITES_START + SITES_N])
        if r[2]
    }
    equip = [
        r
        for r in (cells(x) for x in lines[EQUIP_START : EQUIP_START + EQUIP_N])
        if r[1]
    ]
    names = [
        r
        for r in (cells(x) for x in lines[NAMES_START : NAMES_START + NAMES_N])
        if r[0]
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── stations.csv ────────────────────────────────────────────────────────
    # Every code from the names block (widest coverage), enriched with
    # coordinates and administrative fields where the metadata block has them.
    # Union of both blocks, not just the names block: BLN2, CAC2, CTNU and LUCB
    # appear only in the metadata block, and three of them carry coordinates.
    # Iterating names alone silently dropped them.
    by_code: dict[str, list[str]] = {}
    for n in names:
        if n[0].strip():
            by_code.setdefault(n[0].strip(), n)
    for code in meta:
        by_code.setdefault(code, [code, "", "", ""])

    rows = []
    for code in sorted(by_code):
        n = by_code[code]
        n = n + [""] * (4 - len(n))
        m = meta.get(code, [""] * 28)
        rows.append(
            {
                "station_code": code,
                "name": n[1].strip(),
                "monitoring_method": (n[3] or m[5] or "").strip().lower() or "continuous",
                "status": (m[4] or "").strip().lower().replace(" ", "_"),
                "latitude": norm_float(m[9]),
                "longitude": norm_float(m[11]),
                "municipality": m[15].strip(),
                "province": m[16].strip(),
                "region": m[17].strip(),
                "land_owner": m[13].strip(),
                "network": (m[7] or "").strip(),
                "agency": "PHIVOLCS",  # the site is in PHIVOLCS's inventory; `network` holds the sub-network
                "date_installed": norm_date(m[19]),
                "date_decommissioned": norm_date(m[20]),
                "last_visit": norm_date(m[25]),
                "project": m[26].strip(),
                "collaborator": m[27].strip(),
                "period_constructed_raw": n[2].strip(),
                "source": "phivolcs_inventory",
            }
        )

    # ── Palawan sites carried only by the analysis block ────────────────────
    #
    # Exactly one Palawan site (PLWN, Brooke's Point) is in the PHIVOLCS
    # inventory above, and it has no coordinates anywhere in the document.
    # Three more — Puerto Princesa, El Nido and Kalayaan — appear only here.
    #
    # They are NAMRIA's, not PHIVOLCS': all three sit in the sheet's NAMRIA
    # list, and PAGENET is NAMRIA's national network, which PHIVOLCS receives
    # RINEX from under an MOA. Seeding them unmarked would put another agency's
    # assets in `stations` looking like our own, so `agency` says NAMRIA and
    # `source` says where the row came from.
    #
    # Note for anyone hunting Palawan sites by code: PALA is *Palanas,
    # Masbate* — the code abbreviates the municipality, not the province.
    known = {r["station_code"] for r in rows}
    analysis = [cells(x) for x in lines[ANALYSIS_START : ANALYSIS_START + ANALYSIS_N]]
    for r in analysis:
        for off, agency, src in (
            (0, "", "phivolcs_analysis_block"),
            (NAMRIA_COL, "NAMRIA", "namria_pagenet_list"),
        ):
            if len(r) < off + 4 or not r[off] or "palawan" not in (r[off + 1] or "").lower():
                continue
            code = r[off].strip()
            if code in known:
                continue
            known.add(code)
            rows.append(
                {
                    "station_code": code,
                    "name": r[off + 1].strip(),
                    "monitoring_method": "continuous",
                    "status": "",          # unverified — analysis block, not inventory
                    "latitude": norm_float(r[off + 2]),
                    "longitude": norm_float(r[off + 3]),
                    "municipality": "",
                    "province": "Palawan",
                    "region": "MIMAROPA Region",
                    "land_owner": "",
                    "agency": agency,
                    "date_installed": "",
                    "date_decommissioned": "",
                    "last_visit": "",
                    "project": "",
                    "collaborator": "",
                    "period_constructed_raw": "",
                    "source": src,
                }
            )

    rows.sort(key=lambda r: r["station_code"])

    with (OUT_DIR / "stations.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ── equipment.csv ───────────────────────────────────────────────────────
    eq_rows = []
    for r in equip:
        housing = " / ".join(p for p in (r[12].strip(), r[13].strip()) if p)
        eq_rows.append(
            {
                "station_code": r[1].strip(),
                "date_installed": norm_date(r[2]),
                "date_removed": norm_date(r[3]),
                "vadase": yes_no(r[5]),
                "manufacturer": r[6].strip(),
                "model": r[8].strip(),
                "antenna_manufacturer": r[7].strip(),
                "antenna_model": r[9].strip(),
                "radome_type": r[10].strip(),
                "antenna_location": r[11].strip(),
                "num_channels": norm_int(r[15]),
                "power_source": r[18].strip(),
                "has_internet": yes_no(r[19]),
                "has_lightning_rod": has_lightning(r[20]),
                # Free text, NOT cable_length_m — see the module docstring.
                "housing_notes": housing,
            }
        )

    with (OUT_DIR / "equipment.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(eq_rows[0]))
        w.writeheader()
        w.writerows(eq_rows)

    with_coords = sum(1 for r in rows if r["latitude"] and r["longitude"])
    print(f"stations.csv  {len(rows):3d} rows ({with_coords} with coordinates)")
    print(f"equipment.csv {len(eq_rows):3d} rows")


if __name__ == "__main__":
    main()
