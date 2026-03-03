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


def write_cleaned_plots(plots_dir: Path, selections: dict[str, list[float]]) -> int:
    """
    Strip selected outlier epochs from PLOT files in-place.

    IMPORTANT: vel_line_v8.m does NOT read OUTLIERS.txt — it has its own internal
    rmoutliers() call. The outlier selection from the reviewer must be applied directly
    to the PLOT files before MATLAB runs.

    For each site with a non-empty selection:
      - Backs up the original PLOT file as SITE.bak on the first call.
      - On re-export, always restores from SITE.bak before stripping (idempotent).
      - Removes rows whose decimal year matches (to 4 d.p.) a selected timestamp.
      - Writes the cleaned data back to the PLOT file.

    Returns the total number of rows removed across all sites.
    """
    total_removed = 0
    for site, timestamps in selections.items():
        if not timestamps:
            continue
        plot_path = plots_dir / site
        if not plot_path.exists():
            continue

        # Back up the original on first export; restore from backup on re-export
        # so that the PLOT file always reflects exactly the current selection.
        bak_path = plot_path.with_suffix(".bak")
        if not bak_path.exists():
            bak_path.write_text(plot_path.read_text())

        ts_set = {round(ts, 4) for ts in timestamps}
        lines = bak_path.read_text().splitlines()
        kept: list[str] = []
        for line in lines:
            parts = line.split()
            if not parts:
                continue
            if round(float(parts[0]), 4) in ts_set:
                total_removed += 1
            else:
                kept.append(line)

        plot_path.write_text("\n".join(kept) + ("\n" if kept else ""))

    return total_removed
