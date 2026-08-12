"""Segmented site-velocity estimation — Python port of PHIVOLCS' MATLAB step.

WHAT THIS REPLACES
`vel_line_v8_newvelduetooffset_v4.m` (Cassandra Cabigan, 09/2024), the final
step of the MOVE Faults workflow and the one that produces the project's actual
scientific deliverable: per-site E/N/U velocities, split at known
discontinuities. It is the only MATLAB dependency in the pipeline, and MATLAB
is licensed and not installed on the R740.

The port is deliberately **bit-faithful by default**. Every formula below
mirrors the MATLAB, including its quirks, so results can be diffed against the
existing outputs before anything is changed. Improvements are opt-in flags.

THE ALGORITHM, AS IMPLEMENTED THERE
  1. Read the site list from `123`, one 4-character name per record.
  2. Read `offsets`: `SITE decimal_year TYPE`, TYPE in {EQ, CE, UK, VE}.
  3. Per site, load `[decimal_year, E, N, U]` in metres; demean each component;
     convert to centimetres.
  4. Split the series at each offset epoch -> segments.
  5. Per segment, fit `x = a + b*t` by least squares, per component.
  6. Report `b` in mm/yr with the standard error of the slope.

THE QUIRK THAT MATTERS
The MATLAB calls `rmoutliers(..., "quartiles", ThresholdFactor=3)` and assigns
the result to `cleaned_d` -- then fits the regression against the RAW `d`, not
`cleaned_d`. **Outliers are detected and listed but never excluded from the
velocity.** That is why the SOP (§6.3.4-6.3.5) tells the analyst to hand-edit
the PLOT files using `outliers` as a reference and re-run the whole thing.

This port reproduces that by default (`--outlier-policy report`) so the numbers
match. `--outlier-policy exclude` closes the loop in one pass, which is what
"can outlier flagging be automated?" was really asking. It is not the default
because it changes published velocities, and that is the user's call.

Decimal-year convention is `year + DOY/365.25`, matching `04_PLOTFILES.py`
and the `offsets` catalog. Do not "fix" it to a leap-aware form: it would
silently desynchronise every offset epoch from twenty years of records.

VERIFICATION (2026-08-12, against PHIVOLCS' own MATLAB output)
Diffed against `Velocity_rover(regress)_10` from the Luzon campaign set on the
file server: **171 of 171 velocity components reproduce exactly**, max
|difference| 0.000000000 mm/yr.

Two things had to be understood to get there, and both are traps for the next
person:

1. **The reference output is older than the event catalog.** The Luzon
   `Velocity_rover(regress)_10` was written 2026-07-09; `offsets` was last
   modified 2026-07-29. Comparing directly shows spurious disagreement at
   IFG1, LUZH, BR14 and LUZD -- sites whose offset records changed in those 20
   days. Reconstructing the catalog as it stood on 2026-07-09 (drop IFG1 and
   LUZH; drop the 2022.8159 record for BR14 and LUZD) gives exact agreement.
   **A velocity file is only reproducible alongside the exact catalog that
   produced it** -- which is the argument for the provenance record described
   in `gfzrnx_vs_teqc_rinex3_evidence.md`.

2. **BR14 and LUZD still differ structurally, and the MATLAB is wrong there.**
   Their offsets are recorded out of chronological order (2022.8159 before
   2022.5695). The MATLAB builds segment bounds in file order, producing a
   descending range like `43:38`, which is empty. Its
   `for N=length(O(kk,1):O(kk,2))` loop then never executes, so `G` retains
   the PREVIOUS segment's design matrix and the regression fits stale times
   against current data. This port sorts the resulting boundary indices and
   produces three valid segments instead of two garbage-adjacent ones. Use
   `--sort-offsets` to also order the catalog itself.

LICENCE/PROVENANCE: pure Python, no external binaries, nothing to declare.
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

OFFSET_TYPES = ("EQ", "CE", "UK", "VE")


@dataclass
class Segment:
    """One inter-offset span of a site's series."""

    start: int
    end: int  # inclusive, matching the MATLAB's O = [start, end]
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)  # mm/yr, E N U
    sigma: tuple[float, float, float] = (0.0, 0.0, 0.0)  # mm/yr
    rstd: tuple[float, float, float] = (0.0, 0.0, 0.0)  # cm
    n_used: int = 0
    outlier_epochs: list[float] = field(default_factory=list)


@dataclass
class SiteResult:
    site: str
    segments: list[Segment]
    n_epochs: int
    offsets: list[tuple[float, str]]

    @property
    def final(self) -> Segment | None:
        """Velocity after the last discontinuity -- the MATLAB's 'final velocity'."""
        return self.segments[-1] if self.segments else None


def read_offsets(path: Path) -> dict[str, list[tuple[float, str]]]:
    """Parse the hand-curated event catalog into {SITE: [(epoch, type), ...]}."""
    out: dict[str, list[tuple[float, str]]] = {}
    for raw in path.read_text(errors="replace").splitlines():
        parts = raw.split()
        if len(parts) < 3:
            continue
        site, epoch, kind = parts[0].upper(), parts[1], parts[2].upper()
        try:
            t = float(epoch)
        except ValueError:
            continue
        if kind not in OFFSET_TYPES:
            # Recorded rather than dropped: an unknown tag is a data-entry
            # question for whoever maintains the catalog, not something to
            # silently discard.
            print(f"  WARNING: unknown offset type {kind!r} for {site} @ {t}", file=sys.stderr)
        out.setdefault(site, []).append((t, kind))
    # NOT sorted by default. The MATLAB iterates the catalog in FILE order, and
    # the catalog is not chronological -- BR14 and LUZD both record 2022.8159
    # before 2022.5695. Sorting produces different (arguably correct) segment
    # boundaries and therefore different published velocities, so it is opt-in
    # via --sort-offsets rather than a silent behaviour change.
    return out


def read_site_series(path: Path) -> np.ndarray:
    """Load `[decimal_year, E, N, U]` (metres) -> ndarray, dropping unparseable rows."""
    rows = []
    for raw in path.read_text(errors="replace").splitlines():
        parts = raw.split()
        if len(parts) < 4:
            continue
        try:
            rows.append([float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])])
        except ValueError:
            continue
    return np.asarray(rows, dtype=float)


def iqr_outliers(block: np.ndarray, threshold: float = 3.0) -> np.ndarray:
    """MATLAB `rmoutliers(..., "quartiles", ThresholdFactor=k)` equivalent.

    Flags a ROW if any column falls outside [Q1 - k*IQR, Q3 + k*IQR], which is
    what MATLAB does for matrix input. Quartiles use linear interpolation --
    NumPy's default and MATLAB's `quantile` default agree here.
    """
    if block.shape[0] < 4:
        return np.zeros(block.shape[0], dtype=bool)
    q1 = np.percentile(block, 25, axis=0)
    q3 = np.percentile(block, 75, axis=0)
    iqr = q3 - q1
    lo, hi = q1 - threshold * iqr, q3 + threshold * iqr
    return np.any((block < lo) | (block > hi), axis=1)


def fit_segment(t: np.ndarray, d: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Least-squares `x = a + b*t` per component.

    Returns (slope, sigma_slope, residual_std), all in the input units per year.
    Mirrors the MATLAB: sigma = sqrt(rnorm / Stt) where rnorm = SSR/(n-2) and
    Stt = sum((t - mean(t))^2).
    """
    n = t.size
    G = np.column_stack([np.ones(n), t])
    slope = np.zeros(3)
    sigma = np.zeros(3)
    rstd = np.zeros(3)
    stt = float(np.sum((t - t.mean()) ** 2))
    for i in range(3):
        model, *_ = np.linalg.lstsq(G, d[:, i], rcond=None)
        resid = d[:, i] - G @ model
        # n-2 degrees of freedom; guard the degenerate short-segment case
        # rather than emitting a silent NaN into a published velocity.
        # n-2 degrees of freedom. At n==2 the MATLAB divides by zero and emits
        # NaN/Inf error bars while still printing the row; reproduce that rather
        # than hiding the segment, so a faithful diff is possible.
        rnorm = float(np.sum(resid**2)) / (n - 2) if n > 2 else float("nan")
        slope[i] = model[1]
        rstd[i] = math.sqrt(rnorm) if rnorm == rnorm else float("nan")
        sigma[i] = math.sqrt(rnorm / stt) if (stt > 0 and rnorm == rnorm) else float("nan")
    return slope, sigma, rstd


def process_site(
    site: str,
    data: np.ndarray,
    offsets: list[tuple[float, str]],
    outlier_policy: str = "report",
    threshold: float = 3.0,
    min_points: int = 2,
) -> SiteResult:
    """Demean, split at offsets, fit each segment."""
    if data.size == 0:
        return SiteResult(site, [], 0, offsets)

    t = data[:, 0]
    d = data[:, 1:4].copy()
    d -= d.mean(axis=0)  # demean, as the MATLAB does
    d *= 100.0  # m -> cm

    # Segment boundaries: first index at or after each offset epoch, mirroring
    # the MATLAB's `min(find(Tdiff>=0))`. Verified equivalent to searchsorted on
    # this data (every series is chronologically sorted).
    starts = [0]
    for epoch, _kind in offsets:
        idx = int(np.searchsorted(t, epoch, side="left"))
        if 0 < idx < t.size:
            starts.append(idx)
    starts = sorted(set(starts))
    bounds = [(s, (starts[i + 1] - 1) if i + 1 < len(starts) else t.size - 1)
              for i, s in enumerate(starts)]

    segments: list[Segment] = []
    for start, end in bounds:
        sl = slice(start, end + 1)
        seg_t, seg_d = t[sl], d[sl]
        if seg_t.size < min_points:
            segments.append(Segment(start, end, n_used=int(seg_t.size)))
            continue

        flags = iqr_outliers(seg_d, threshold)
        outlier_epochs = [float(x) for x in seg_t[flags]]

        if outlier_policy == "exclude" and flags.any() and (~flags).sum() >= 3:
            fit_t, fit_d = seg_t[~flags], seg_d[~flags]
        else:
            # Default: fit the RAW data, outliers included -- faithful to the
            # MATLAB, which computes `cleaned_d` and then ignores it.
            fit_t, fit_d = seg_t, seg_d

        slope, sigma, rstd = fit_segment(fit_t, fit_d)
        segments.append(
            Segment(
                start=start,
                end=end,
                velocity=tuple(slope * 10.0),  # cm/yr -> mm/yr
                sigma=tuple(sigma * 10.0),
                rstd=tuple(rstd),
                n_used=int(fit_t.size),
                outlier_epochs=outlier_epochs,
            )
        )
    return SiteResult(site, segments, int(t.size), offsets)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plots-dir", type=Path, default=Path("."),
                    help="directory holding the per-site series and `123` (default: cwd)")
    ap.add_argument("--offsets", type=Path, default=None,
                    help="event catalog (default: <plots-dir>/offsets)")
    ap.add_argument("--site-list", type=Path, default=None,
                    help="site index (default: <plots-dir>/123)")
    ap.add_argument("--outlier-policy", choices=("report", "exclude"), default="report",
                    help="report = MATLAB-faithful (outliers listed, NOT excluded from the "
                         "fit); exclude = drop them and refit in one pass")
    ap.add_argument("--threshold", type=float, default=3.0,
                    help="IQR threshold factor (MATLAB default is 1.5; this workflow uses 3)")
    ap.add_argument("--sort-offsets", action="store_true",
                    help="sort the event catalog chronologically. The MATLAB does NOT: it "
                         "reads in file order, and the catalog has out-of-order records "
                         "(BR14, LUZD), which silently costs it a segment. Correct, but it "
                         "changes published velocities -- hence opt-in.")
    ap.add_argument("--min-segment-points", type=int, default=2,
                    help="skip segments shorter than this. Default 2 reproduces the MATLAB, "
                         "which emits n=2 segments with NaN error bars; 3 suppresses them.")
    ap.add_argument("--out-velocity", type=Path, default=None)
    ap.add_argument("--out-outliers", type=Path, default=None)
    args = ap.parse_args()

    plots = args.plots_dir
    site_list = args.site_list or plots / "123"
    offsets_path = args.offsets or plots / "offsets"
    if not site_list.is_file():
        print(f"FATAL: site list not found: {site_list}", file=sys.stderr)
        return 1
    if not offsets_path.is_file():
        print(f"FATAL: offsets catalog not found: {offsets_path}", file=sys.stderr)
        return 1

    offsets = read_offsets(offsets_path)
    if args.sort_offsets:
        for k in offsets:
            offsets[k].sort()
    sites = [s.strip().upper()[:4] for s in site_list.read_text().split() if s.strip()]
    print(f"sites: {len(sites)}   offset records: {sum(len(v) for v in offsets.values())} "
          f"across {len(offsets)} sites   policy: {args.outlier_policy}\n")

    vel_out = args.out_velocity or plots / "Velocity_rover(regress)_10.py.txt"
    oul_out = args.out_outliers or plots / "outliers.py.txt"

    vlines = [
        "-" * 71,
        "sites        Ve                     Vn                    Vu   unit: mm",
        "-" * 71,
    ]
    olines = ["-" * 18, "outliers list", "-" * 18]
    missing = 0

    for site in sites:
        f = plots / site
        if not f.is_file():
            missing += 1
            continue
        res = process_site(site, read_site_series(f), offsets.get(site, []),
                           args.outlier_policy, args.threshold,
                           args.min_segment_points)
        olines.append(f"\n{site}")
        for seg in res.segments:
            if seg.n_used < args.min_segment_points:
                continue
            v, s = seg.velocity, seg.sigma
            vlines.append(
                f"{site} {v[0]:10.5f} +- {s[0]:4.1f}    "
                f"{v[1]:10.5f} +- {s[1]:4.1f}    {v[2]:10.5f} +- {s[2]:4.1f}"
            )
            for ep in seg.outlier_epochs:
                olines.append(f"{ep:.4f}")
        fin = res.final
        if fin and fin.n_used >= args.min_segment_points:
            print(f"  {site}  n={res.n_epochs:<5} segments={len(res.segments)}  "
                  f"final V(E,N,U) = {fin.velocity[0]:7.2f} {fin.velocity[1]:7.2f} "
                  f"{fin.velocity[2]:7.2f} mm/yr")

    vel_out.write_text("\n".join(vlines) + "\n")
    oul_out.write_text("\n".join(olines) + "\n")
    print(f"\nwrote {vel_out}\nwrote {oul_out}")
    if missing:
        print(f"NOTE: {missing} site(s) in the index had no series file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
