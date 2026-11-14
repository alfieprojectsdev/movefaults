"""
File I/O for the PHIVOLCS GNSS velocity pipeline file formats.

Handles:
  123         — master site list (one 4-char code per line)
  PLOT files  — decimal_year  east_m  north_m  up_m (whitespace-separated)
  offsets     — SITE  decimal_year  TYPE (EQ/CE/VE/UK)
  OUTLIERS.txt — output: SITE  decimal_year (one outlier epoch per line)
"""

import os
import shutil
from collections import Counter
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
    plots_dir: Path, site: str, *, from_backup: bool = False
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Parse a PLOT file (or, with `from_backup`, its SITE.bak) into (t, e, n, u).

    PLOT file format (from RUNX_v2.py):
        decimal_year  east_m  north_m  up_m
    Values are in metres; mean-centring and cm conversion happen in regression.py.
    """
    path = plots_dir / site
    if from_backup:
        path = path.with_suffix(".bak")
    rows = [line.split() for line in _data_lines(path.read_text())]
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


def _data_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def _is_stripped_copy(plot_lines: list[str], bak_lines: list[str]) -> bool:
    """True when every row of the PLOT file is also in the backup.

    That is what an earlier export leaves behind. A PLOT file regenerated since
    (new epochs, or reprocessed coordinates) has rows the backup lacks.
    """
    remaining = Counter(bak_lines)
    remaining.subtract(Counter(plot_lines))
    return all(count >= 0 for count in remaining.values())


def previously_stripped(plots_dir: Path, site: str) -> list[float] | None:
    """
    Epochs an earlier export stripped from this site's PLOT file.

    None when there is nothing to restore from: no SITE.bak, or a PLOT file
    regenerated since (it has rows the backup lacks). Otherwise the epochs of
    the backup rows missing from the PLOT file, possibly an empty list.
    """
    plot_path = plots_dir / site
    bak_path = plot_path.with_suffix(".bak")
    if not (plot_path.exists() and bak_path.exists()):
        return None
    current = _data_lines(plot_path.read_text())
    original = _data_lines(bak_path.read_text())
    if not _is_stripped_copy(current, original):
        return None
    missing = Counter(original) - Counter(current)
    return [float(line.split()[0]) for line in missing.elements()]


def write_cleaned_plots(plots_dir: Path, selections: dict[str, list[float]]) -> int:
    """
    Strip selected outlier epochs from PLOT files in-place.

    IMPORTANT: vel_line_v8.m does NOT read OUTLIERS.txt — it has its own internal
    rmoutliers() call. The outlier selection from the reviewer must be applied directly
    to the PLOT files before MATLAB runs.

    For each site in `selections`:
      - The first export copies the PLOT file to SITE.bak, byte for byte.
      - Every export rebuilds the PLOT file from SITE.bak minus the current
        selection, so exporting twice gives the same file, and an empty
        selection restores the original.
      - If the PLOT file has rows the backup lacks, it was regenerated after
        the last export: it replaces the backup before stripping, so new epochs
        are not lost.
      - Rows match a selected timestamp when both round to the same 4 d.p.

    Known limit: a regenerated PLOT file whose rows are all in the old backup
    (a shorter span, nothing else changed), or one with rows deleted by hand,
    is taken for an earlier export, and the backup's extra rows come back.
    Delete SITE.bak after either to avoid it.

    Returns the total number of rows removed across all sites.
    """
    total_removed = 0
    for site, timestamps in selections.items():
        plot_path = plots_dir / site
        if not plot_path.exists():
            continue
        bak_path = plot_path.with_suffix(".bak")
        current = _data_lines(plot_path.read_text())

        if bak_path.exists():
            original = _data_lines(bak_path.read_text())
            if not _is_stripped_copy(current, original):
                shutil.copyfile(plot_path, bak_path)
                original = current
        elif timestamps:
            shutil.copyfile(plot_path, bak_path)
            original = current
        else:
            continue  # never exported and nothing selected: leave it alone

        ts_set = {round(ts, 4) for ts in timestamps}
        kept: list[str] = []
        for line in original:
            if round(float(line.split()[0]), 4) in ts_set:
                total_removed += 1
            else:
                kept.append(line)

        # Write beside the file and rename over it: a PLOT file truncated by an
        # interrupted write would look regenerated to the next export and
        # replace the backup.
        tmp_path = plot_path.with_name(plot_path.name + ".tmp")
        tmp_path.write_text("\n".join(kept) + ("\n" if kept else ""))
        os.replace(tmp_path, plot_path)

    return total_removed
