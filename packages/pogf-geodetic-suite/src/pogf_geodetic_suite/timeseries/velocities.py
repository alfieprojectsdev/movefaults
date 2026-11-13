"""
Velocities for a whole PLOT directory, written the way the MATLAB writes them.

`vel_line_v8_newvelduetooffset_v4.m` reads a site list (`123`), one PLOT file
per site and the `offsets` catalog, and writes two files:

- `Velocity_rover(regress)_10`: one line per segment per site, in mm/yr;
- `outliers`: per site, the epochs the IQR rule flagged.

`analysis.estimate_velocity` already reproduces those numbers (161 of 165
components to 5e-6 mm/yr on the Luzon set, see its module docstring), but
nothing ran it over a directory and wrote those files. This module does, so a
processing staff member can compare its output with their own MATLAB run file
for file, and so `compare_velocity_tables` can do that comparison for them.

What it adds that the MATLAB does not: a `velocities_manifest.json` beside the
outputs, recording the offsets catalog's sha256, the outlier mode, the sites
that could not be fitted and why, and the sha256 of every file written. A
velocity table is only meaningful with the exact catalog that produced it
(`scripts/compare_velocity_outlier_policy.py` explains how that has bitten).

Known, deliberate differences from the MATLAB:

- A segment with fewer than 3 epochs is not fitted, so it has no line. The
  MATLAB fits it anyway and writes NaN error bars (KA08 on the Luzon set).
- Offsets are applied in date order. The MATLAB applies them in catalog order,
  so a catalog with a station's records out of order makes it fit the wrong
  intervals (BR14, LUZD on the Luzon set).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .analysis import OffsetEvent, VelocityResult, estimate_velocity

TABLE_NAME = "Velocity_rover(regress)_10"
OUTLIERS_NAME = "outliers"
MANIFEST_NAME = "velocities_manifest.json"

_RULE = "-" * 71
TABLE_HEADER = (
    f"{_RULE}\n"
    "sites        Ve                     Vn                    Vu   unit: mm\n"
    f"{_RULE}\n"
)

# The MATLAB's own line format: velocities to 5 decimals, sigmas to 1.
#   fprintf('%s %10.5f +- %4.1f    %10.5f +- %4.1f    %10.5f +- %4.1f\n', ...)
# MATLAB prints NaN/Inf, Python nan/inf: accept both, or a non-finite line
# would vanish from the comparison instead of showing as a difference.
_NUM = r"(-?[\d.]+|-?(?i:nan|inf))"
_LINE = re.compile(
    rf"^(\S+)\s+{_NUM}\s+\+-\s+{_NUM}\s+{_NUM}\s+\+-\s+{_NUM}"
    rf"\s+{_NUM}\s+\+-\s+{_NUM}\s*$"
)


@dataclass(frozen=True)
class SiteFailure:
    site: str
    reason: str


def read_site_list(path: Path) -> list[str]:
    """The `123` file: whitespace-separated PLOT file names, in run order."""
    return [s for s in path.read_text(encoding="utf-8").split() if s]


def load_plot_file(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """A PLOT file: decimal year, then E N U in metres. Extra columns are ignored,
    as the MATLAB's `rawdata(:,1:4)` ignores them."""
    arr = np.loadtxt(path, ndmin=2)
    if arr.shape[1] < 4:
        raise ValueError(f"{path.name}: expected at least 4 columns, found {arr.shape[1]}")
    return arr[:, 0], arr[:, 1:4]


def compute_velocities(
    plot_dir: Path,
    sites: Iterable[str],
    catalog: Mapping[str, list[OffsetEvent]],
    *,
    exclude_outliers: bool,
    iqr_factor: float = 3.0,
) -> tuple[
    list[tuple[str, VelocityResult]], list[SiteFailure], list[SiteFailure], dict[str, str]
]:
    """Fit every site in `sites`, in that order.

    A site that cannot be fitted is reported, not raised, so one bad file does
    not cost the other sites their velocities. The caller must show the
    failures; this function never drops a site silently.

    Returns (results, failures, short, trailing_dropped): `short` names fitted
    sites that lost a segment of fewer than 3 epochs, and `trailing_dropped`
    maps station code to reason where that segment was the final one, shaped
    for `gmt.write_psvelo(withhold=...)`.
    """
    results: list[tuple[str, VelocityResult]] = []
    failures: list[SiteFailure] = []
    short: list[SiteFailure] = []
    trailing_dropped: dict[str, str] = {}
    for name in sites:
        path = plot_dir / name
        if not path.is_file():
            failures.append(SiteFailure(name, "no PLOT file"))
            continue
        # The MATLAB matches the catalog on the file name's first 4 characters.
        code = name[:4].upper()
        try:
            t, enu = load_plot_file(path)
            res = estimate_velocity(
                t, enu,
                offsets=catalog.get(code),
                outlier_iqr_factor=iqr_factor,
                station=code,
                exclude_outliers=exclude_outliers,
            )
        except ValueError as exc:
            # estimate_velocity raises when no segment has 3 or more epochs,
            # so every result appended below has at least one segment.
            failures.append(SiteFailure(name, str(exc)))
            continue
        results.append((name, res))
        # estimate_velocity skips a segment of fewer than 3 epochs without
        # saying so. Name it: a dropped TRAILING segment makes the last line
        # in the table the pre-offset rate, which a map would draw as current.
        fitted = sum(len(s.rows) for s in res.segments)
        if fitted < len(t):
            last_fitted = res.segments[-1].t_end
            trailing = bool(np.max(t) > last_fitted)
            short.append(SiteFailure(
                name,
                f"{len(t) - fitted} epoch(s) in segment(s) of fewer than 3 epochs "
                "not fitted" + ("; the final segment is one of them, so the last "
                                "line is NOT the current rate" if trailing else ""),
            ))
            if trailing:
                trailing_dropped[code] = (
                    f"final segment after {last_fitted:.4f} has fewer than 3 epochs"
                )
    return results, failures, short, trailing_dropped


def format_velocity_table(results: Iterable[tuple[str, VelocityResult]]) -> str:
    """`Velocity_rover(regress)_10`, byte for byte in the MATLAB's layout."""
    out = [TABLE_HEADER]
    for name, res in results:
        for s in res.segments:
            out.append(
                f"{name} {s.ve_mm_yr:10.5f} +- {s.sig_ve:4.1f}    "
                f"{s.vn_mm_yr:10.5f} +- {s.sig_vn:4.1f}    "
                f"{s.vu_mm_yr:10.5f} +- {s.sig_vu:4.1f}\n"
            )
    return "".join(out)


def format_outliers(results: Iterable[tuple[str, VelocityResult]]) -> str:
    """The MATLAB's `outliers` file: the flagged epochs per site, every segment."""
    out = ["------------------\noutliers list\n------------------"]
    for name, res in results:
        out.append(f"\n{name}\n")
        for s in res.segments:
            out.extend(f"{t:4.4f}\n" for t in s.outlier_epochs)
    return "".join(out)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(
    path: Path,
    *,
    plot_dir: Path,
    site_list: Path,
    offsets: Path | None,
    outlier_mode: str,
    iqr_factor: float,
    reference: str | None,
    n_sites: int,
    failures: list[SiteFailure],
    written: Iterable[Path],
    short_segments: Iterable[SiteFailure] = (),
    missing_positions: Iterable[str] = (),
) -> None:
    """Record what produced the outputs, beside them."""
    manifest = {
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": "pogf-timeseries velocities",
        "plot_dir": str(plot_dir),
        "site_list": {"path": str(site_list), "sha256": sha256_file(site_list)},
        "offsets": (
            {"path": str(offsets), "sha256": sha256_file(offsets)} if offsets else None
        ),
        "outlier_mode": outlier_mode,
        "iqr_factor": iqr_factor,
        "reference": reference,
        "sites_listed": n_sites,
        "sites_fitted": n_sites - len(failures),
        "failures": [{"site": f.site, "reason": f.reason} for f in failures],
        "short_segments": [{"site": f.site, "reason": f.reason} for f in short_segments],
        "missing_positions": list(missing_positions),
        "outputs": {p.name: sha256_file(p) for p in written},
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Comparing two tables
# ---------------------------------------------------------------------------

# A table carries velocities to 5 decimals and sigmas to 1, so two values agree
# when they round to the same printed number: half a unit in the last place.
VEL_TOL = 5e-6
SIG_TOL = 0.05


@dataclass(frozen=True)
class TableRow:
    ve: float
    sve: float
    vn: float
    svn: float
    vu: float
    svu: float


def parse_velocity_table(path: Path) -> dict[str, list[TableRow]]:
    """Every segment line of a `Velocity_rover(regress)_10`, per site, in order."""
    out: dict[str, list[TableRow]] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        vals = [float(x) for x in m.groups()[1:]]
        out.setdefault(m.group(1), []).append(TableRow(*vals))
    return out


@dataclass(frozen=True)
class SiteComparison:
    site: str
    status: str            # "match", "differ", "segments", "only-ours", "only-theirs"
    worst_velocity: float  # mm/yr, largest |difference| over all compared lines
    worst_sigma: float
    detail: str = ""


def compare_velocity_tables(ours: Path, theirs: Path) -> list[SiteComparison]:
    """Compare two tables site by site and segment by segment.

    "match" means every velocity agrees to VEL_TOL and every sigma to SIG_TOL,
    which is "prints the same" at the tables' own precision. A different number
    of segments is reported as such, because it means a different catalog or a
    different segment rule, not a different fit.
    """
    a = parse_velocity_table(ours)
    b = parse_velocity_table(theirs)
    rows: list[SiteComparison] = []
    for site in sorted(set(a) | set(b)):
        if site not in b:
            rows.append(SiteComparison(site, "only-ours", 0.0, 0.0))
            continue
        if site not in a:
            rows.append(SiteComparison(site, "only-theirs", 0.0, 0.0))
            continue
        sa, sb = a[site], b[site]
        if len(sa) != len(sb):
            rows.append(SiteComparison(
                site, "segments", 0.0, 0.0, f"{len(sa)} segment(s) here, {len(sb)} there",
            ))
            continue
        va = np.array([[r.ve, r.vn, r.vu] for r in sa])
        vb = np.array([[r.ve, r.vn, r.vu] for r in sb])
        qa = np.array([[r.sve, r.svn, r.svu] for r in sa])
        qb = np.array([[r.sve, r.svn, r.svu] for r in sb])
        # np.max, not the builtin: the builtin's result with a NaN depends on
        # argument order, and a NaN on either side must count as a difference.
        wv = float(np.max(np.abs(va - vb)))
        ws = float(np.max(np.abs(qa - qb)))
        ok = wv <= VEL_TOL and ws <= SIG_TOL  # False when either is NaN
        rows.append(SiteComparison(site, "match" if ok else "differ", wv, ws))
    return rows
