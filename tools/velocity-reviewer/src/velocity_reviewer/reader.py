"""
File I/O for the PHIVOLCS GNSS velocity pipeline file formats.

Handles:
  123         — master site list (one 4-char code per line)
  PLOT files  — decimal_year  east_m  north_m  up_m (whitespace-separated)
  offsets     — SITE  decimal_year  TYPE (EQ/CE/VE/UK)
  OUTLIERS.txt — output: SITE  decimal_year (one outlier epoch per line)
"""

from pathlib import Path

import numpy as np


def read_123(plots_dir: Path) -> list[str]:
    """Return ordered list of site codes from the '123' master site list file."""
    sites = []
    for line in (plots_dir / "123").read_text().splitlines():
        site = line.strip()
        if site:
            sites.append(site[:4].upper())
    return sites


def read_plot(
    plots_dir: Path, site: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Parse a PLOT file into (t, e, n, u) arrays.

    PLOT file format (from RUNX_v2.py):
        decimal_year  east_m  north_m  up_m
    Values are in metres; mean-centring and cm conversion happen in regression.py.
    """
    rows = [
        line.split()
        for line in (plots_dir / site).read_text().splitlines()
        if line.strip()
    ]
    t = np.array([float(r[0]) for r in rows])
    e = np.array([float(r[1]) for r in rows])
    n = np.array([float(r[2]) for r in rows])
    u = np.array([float(r[3]) for r in rows])
    return t, e, n, u


def read_offsets(plots_dir: Path) -> dict[str, list[tuple[float, str]]]:
    """
    Parse the 'offsets' discontinuity file.

    Format: SITE  decimal_year  TYPE
    Returns {site_upper: [(decimal_year, type_tag), ...]}
    """
    offsets_file = plots_dir / "offsets"
    result: dict[str, list[tuple[float, str]]] = {}
    if not offsets_file.exists():
        return result
    for line in offsets_file.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            site = parts[0].upper()
            year = float(parts[1])
            tag = parts[2].upper()
            result.setdefault(site, []).append((year, tag))
    return result


def write_outliers_txt(plots_dir: Path, selections: dict[str, list[float]]) -> Path:
    """
    Write OUTLIERS.txt in the format expected by vel_line_v8.m:
        SITE  decimal_year   (one epoch per line)

    Uses the same format string as the original outlier_input-site.py:
        '{site:<4s} {decimal_year}'
    """
    out_path = plots_dir / "OUTLIERS.txt"
    lines: list[str] = []
    for site in sorted(selections):
        for ts in sorted(selections[site]):
            lines.append(f"{site:<4s} {ts:.4f}\n")
    out_path.write_text("".join(lines))
    return out_path
