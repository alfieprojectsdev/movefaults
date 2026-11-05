"""
Read-only status of one station's time series, as a JSON-ready dict.

This is the endpoint the console's Time series screen waits on. It runs no
pipeline step and writes nothing: it reads daily final CRD files, builds the
ENU series relative to a reference station (`crd_pipeline`), looks up the
station's events in the `offsets` catalog (`offsets_catalog`), and fits the
offset-aware segmented velocity (`analysis.estimate_velocity`, the port
verified against PHIVOLCS' MATLAB). It adds no science of its own; what it
adds is one result a web page can plot without further arithmetic.

Two entry points:

    station_status(crd_dir, station, reference, offsets_catalog=...)
        reads CRD files from disk
    series_status(t, enu_m, station=..., offsets=...)
        the same result from arrays already in memory; this is the pure part,
        and what the tests exercise directly

and one CLI subcommand, `pogf-timeseries status` (see `cli.py`).

OUTLIERS ARE FLAGGED, NEVER DROPPED
-----------------------------------
The flags are the fit's own: `estimate_velocity` reports, per segment, which
rows it assigned and which it flagged (`SegmentVelocity.rows`, `.outlier_rows`),
and this module copies them rather than re-running the rule. The rule today is
`analysis._detect_outliers_iqr`, per segment: an epoch is flagged when ANY of its
E, N, U values lies more than `outlier_iqr_factor` (default 3.0, as in
`vel_line_v8`) interquartile ranges outside that segment's quartiles. It runs on
the raw values, not on residuals from the fit; see "Known weakness" below.

Every epoch read is returned in `series`, flagged or not. Whether a flag also
changes the velocity is `outlier_mode`:

    "record"   (DEFAULT) flagged epochs are reported and kept in the fit.
               Identical to `estimate_velocity(exclude_outliers=False)`, which
               is the setting that reproduces PHIVOLCS' published velocities.
    "exclude"  flagged epochs are left out of the fit (but still returned in
               `series`). Identical to `exclude_outliers=True`.

Whether outliers should be excluded from the published fit is an OPEN team
decision as of 2026-11-04 (`docs/SETTLED.md` §6), which is why this defaults to
"record". Note that `analysis.estimate_velocity` itself defaults to excluding,
following the 2026-08-13 entry in `velocity_outlier_policy_delta.md`; this
module passes the flag explicitly and does not change that default. The echoed
`outlier_rule.mode` says which one produced the numbers.

"exclude" removes what the statistic flagged, not what an analyst confirmed.
There is no confirmation input here: that is the reviewer's job, and the
decision-support posture in `automation_stages.md` keeps it with a person.

Known weakness, inherited and not fixed here: IQR on raw values lets a strong
trend inflate the spread, so a horizontal outlier on a fast-moving site can sit
inside the fences unflagged. `automation_stages.md` (stage 3, item 1) proposes
iterative detection on residuals. `tools/velocity-reviewer` already uses a
residual-based rule, so the two tools can flag different epochs for the same
site.

RESULT SHAPE  (schema "pogf.timeseries.status/1")
-------------------------------------------------
Units are in the key names. Times are decimal years in the project's
convention, `year + DOY/365.25` (`crd_pipeline.session_to_decimal_year`; settled,
do not "correct"). Arrays in `series` are columnar and index-aligned, so a
plotting library can take them as they are. The dict contains only str, int,
float, bool, None, lists and dicts, and `json.dumps(result, allow_nan=False)`
succeeds on any result this module returns.

    {
      "schema": "pogf.timeseries.status/1",
      "station": "SYN1",
      "reference": "REF0" | null,
      "offsets_catalog": {"path": str, "sha256": str} | null,
      "outlier_rule": {
        "method": "iqr", "factor": 3.0, "scope": "per_segment",
        "on": "raw_values", "mode": "record" | "exclude"
      },
      "origin_m": {"e": float, "n": float, "u": float},
          # ENU of the FIRST epoch relative to the reference station, metres.
          # Series and fit lines below are millimetres relative to this, so
          # absolute ENU = origin_m * 1000 + series value (mm).
      "series": {
        "t":        [float, ...],      # decimal year, ascending
        "e_mm":     [float, ...],
        "n_mm":     [float, ...],
        "u_mm":     [float, ...],
        "outlier":  [bool, ...],       # flagged by the rule above
        "in_fit":   [bool, ...],       # used by the velocity fit
        "excluded": [bool, ...],       # left out because a person confirmed it
                                       # as an outlier (exclude_epochs); the
                                       # rule's "outlier" flag is unaffected
        "segment":  [int | null, ...]  # index into "segments"; null when the
                                       # epoch fell in an interval too short
                                       # to fit (fewer than 3 epochs)
      },
      "offsets": [                     # every catalog event for this station
        {"t": float, "type": "EQ", "label": "earthquake",
         "within_span": bool}          # true: inside the observed span, so it
      ],                               # splits the series into segments
      "segments": [
        {"index": int,
         "t_start": float, "t_end": float, "span_yr": float,
         "n_epochs": int,              # epochs in the segment
         "n_fit": int,                 # epochs used by the fit
         "n_outliers": int,
         "velocity_mm_yr": {"e": float, "n": float, "u": float},
         "sigma_mm_yr":    {"e": float, "n": float, "u": float},  # 1-sigma
         "r2":             {"e": float, "n": float, "u": float},
         "short_span": bool,           # span_yr < min_span_years
         "line": {"t": [t_start, t_end],          # the fitted line at the
                  "e_mm": [a, b], "n_mm": [a, b], # segment's ends, same
                  "u_mm": [a, b]}}                # frame as "series"
      ],
      "velocity": {                    # the final segment: the one published
        "segment": int,
        "velocity_mm_yr": {...}, "sigma_mm_yr": {...},
        "span_yr": float, "short_span": bool,
        "covers_latest_epoch": bool    # false: the newest epochs sit in an
      },                               # interval too short to fit, so this is
                                       # the rate before the latest event
      "min_span_years": float,
      "exclusions": {                  # what exclude_epochs asked for
        "requested": int, "matched": int,
        "unmatched": [float, ...]      # asked for, but no epoch at that time
      },
      "warnings": [str, ...]           # empty list = nothing to say
    }

`station_status`, which knows the reference, adds two more: `reference_distance_deg`
(degrees of arc from the station to the reference) and `reference_warning` (a
sentence when that is over `REFERENCE_WARN_DEG`, else null; also in `warnings`).
East, North and Up are the reference's axes, as in RUNX_v2.py, so a far-away
reference rotates a station's motion between them. The method is kept, so the
numbers stay comparable with production; the reader is told (`docs/SETTLED.md`
section 3).

`velocity` is the final segment because that is what `VelocityResult.final_
velocity`, `make_velocity_field.py` and the published files all use. When
`short_span` is true the number is the slope of too little data to mean
anything (`velocity_outlier_policy_delta.md`, six Luzon sites); it is still
returned, so that a page can show it struck through rather than not at all.
The threshold is `gmt.MIN_SPAN_YEARS`, the one the velocity-field writer uses
to withhold a station.
"""
from __future__ import annotations

import hashlib
import re
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from .analysis import OffsetEvent, OffsetType, estimate_velocity
from .crd_pipeline import (
    CrdDirs,
    crd_datums,
    crd_directory_to_enu,
    crd_dirs_text,
    days_without_station,
    session_to_decimal_year,
)
from .gmt import MIN_SPAN_YEARS
from .offsets_catalog import load_offsets_catalog

__all__ = [
    "REFERENCE_WARN_DEG",
    "SCHEMA",
    "OutlierMode",
    "series_status",
    "station_status",
]

SCHEMA = "pogf.timeseries.status/1"

# A judgement, not a physical limit: at 5 degrees about 9% of a station's motion
# relative to the reference is rotated between components, which for 30 mm/yr is
# about 2.6 mm/yr, as large as a typical 1-sigma on Up. Measured for ALAB: at most
# 0.4 mm/yr with a reference 1.1 degrees away, 7.7 mm/yr at 19.4 degrees.
REFERENCE_WARN_DEG = 5.0
_EARTH_RADIUS_M = 6_371_000.0

_TYPE_LABELS = {
    OffsetType.EQ: "earthquake",
    OffsetType.CE: "equipment change",
    OffsetType.VE: "volcanic",
    OffsetType.UK: "unknown",
}


class OutlierMode(str, Enum):
    """What a flagged outlier does to the velocity fit. See module docstring."""
    RECORD = "record"     # flag only; keep in the fit (default)
    EXCLUDE = "exclude"   # flag and leave out of the fit


def _enu(vec: np.ndarray) -> dict[str, float]:
    return {"e": float(vec[0]), "n": float(vec[1]), "u": float(vec[2])}


def series_status(
    t: np.ndarray,
    enu_m: np.ndarray,
    *,
    station: str,
    reference: str | None = None,
    offsets: list[OffsetEvent] | None = None,
    outlier_mode: OutlierMode | str = OutlierMode.RECORD,
    outlier_iqr_factor: float = 3.0,
    min_span_years: float = MIN_SPAN_YEARS,
    offsets_catalog: dict[str, str] | None = None,
    exclude_epochs: list[float] | None = None,
) -> dict[str, Any]:
    """
    Status of one ENU series already in memory.

    Args:
        t:                  Decimal years, shape (N,). Need not be sorted.
        enu_m:              ENU in metres relative to the reference, (N, 3).
        station:            Station code, echoed in the result.
        reference:          Reference station code, echoed; None if unknown.
        offsets:            This station's events. None or [] fits one segment
                            and says so in `warnings`.
        outlier_mode:       "record" (default) or "exclude".
        outlier_iqr_factor: IQR multiplier for the outlier rule.
        min_span_years:     Below this a segment is marked `short_span`.
        offsets_catalog:    Provenance to echo ({"path", "sha256"}), if the
                            offsets came from a file.
        exclude_epochs:     Decimal years of epochs a person confirmed as
                            outliers: left out of the fit in every mode, and
                            marked in `series.excluded`. Matched exactly, so
                            pass the times as the series carries them (two
                            rows at one time are both excluded). Times with no
                            epoch are listed in `exclusions.unmatched`.

    Returns:
        The dict described in the module docstring.

    Raises:
        ValueError: from `estimate_velocity`, e.g. no segment has 3 epochs,
                    or "exclude" leaves a segment with fewer than 3.
    """
    mode = OutlierMode(outlier_mode)
    t = np.asarray(t, dtype=float)
    enu_m = np.asarray(enu_m, dtype=float)
    if t.ndim != 1 or enu_m.shape != (t.size, 3):
        raise ValueError(f"Station {station!r}: expected t (N,) and enu_m (N, 3).")
    if t.size == 0:
        raise ValueError(f"Station {station!r}: empty series.")
    if not (np.all(np.isfinite(t)) and np.all(np.isfinite(enu_m))):
        # A NaN would make the fit NaN and the JSON invalid; refuse here, where
        # the cause is still nameable.
        raise ValueError(f"Station {station!r}: series contains NaN or inf.")
    # Both are echoed into the result, so a NaN or inf here would break the
    # allow_nan=False promise. A factor <= 0 flags (nearly) every epoch.
    if not (np.isfinite(outlier_iqr_factor) and outlier_iqr_factor > 0):
        raise ValueError(f"outlier_iqr_factor must be finite and > 0, got {outlier_iqr_factor!r}")
    if not (np.isfinite(min_span_years) and min_span_years >= 0):
        raise ValueError(f"min_span_years must be finite and >= 0, got {min_span_years!r}")

    order = np.argsort(t, kind="stable")
    t, enu_m = t[order], enu_m[order]
    events = sorted(offsets or [], key=lambda e: e.date)

    asked = np.asarray(exclude_epochs if exclude_epochs is not None else [], dtype=float)
    if asked.ndim != 1 or not np.all(np.isfinite(asked)):
        raise ValueError(f"Station {station!r}: exclude_epochs must be finite decimal years.")
    excluded = np.isin(t, asked)
    unmatched = sorted({float(x) for x in asked} - {float(x) for x in t[excluded]})

    result = estimate_velocity(
        t, enu_m,
        offsets=events,
        outlier_iqr_factor=outlier_iqr_factor,
        station=station,
        exclude_outliers=(mode is OutlierMode.EXCLUDE),
        exclude_rows=excluded,
    )

    origin = enu_m[0]
    rel_mm = (enu_m - origin) * 1000.0

    # Per-epoch segment index and outlier flag, copied BY ROW from the fit
    # (`t` and `enu_m` here are what was passed to `estimate_velocity`, so its
    # row numbers index them directly). Matching `seg.outlier_epochs` by value
    # instead would flag both copies of a duplicated day when only one is an
    # outlier (the F1_/FIN_ case warned about below), and re-running the rule
    # here would be a second copy of it that drifts the day the fit's changes.
    seg_of = np.full(t.size, -1, dtype=int)
    outlier = np.zeros(t.size, dtype=bool)
    for k, seg in enumerate(result.segments):
        seg_of[list(seg.rows)] = k
        outlier[list(seg.outlier_rows)] = True
    assigned = seg_of >= 0
    segment_idx: list[int | None] = [int(k) if k >= 0 else None for k in seg_of]
    in_fit = assigned & ~outlier if mode is OutlierMode.EXCLUDE else assigned
    in_fit = in_fit & ~excluded

    warnings: list[str] = []
    if offsets is None:
        warnings.append("no offsets supplied: fitted as a single segment")
    elif not events:
        warnings.append("no offset events for this station: fitted as a single segment")
    # An interval with fewer than 3 epochs is skipped by estimate_velocity
    # without a word. When it is the LAST interval, its final_velocity is the
    # rate from BEFORE the latest event: a plausible number for the wrong epoch.
    n_after = int((t > result.segments[-1].t_end).sum())
    covers_latest = n_after == 0
    if not covers_latest:
        warnings.append(
            f"the latest {n_after} epoch(s), after the last offset, are too few "
            "to fit (< 3): 'velocity' is the rate BEFORE that offset"
        )
    # Unfitted epochs before the first segment or between segments; the
    # trailing ones are reported above.
    n_unfit = int((~assigned).sum()) - n_after
    if n_unfit:
        warnings.append(
            f"{n_unfit} epoch(s) lie in intervals (before or between offsets) "
            "with fewer than 3 epochs; no velocity was fitted there (segment = null)"
        )
    n_dup = t.size - np.unique(t).size
    if n_dup:
        warnings.append(
            f"{n_dup} duplicate epoch(s): two files for one day? "
            "(e.g. F1_ and FIN_ for the same session in one directory)"
        )

    segments: list[dict[str, Any]] = []
    for k, seg in enumerate(result.segments):
        members = seg_of == k
        fit = members & in_fit
        vel = np.array([seg.ve_mm_yr, seg.vn_mm_yr, seg.vu_mm_yr])
        # OLS passes through (mean t, mean d) of the epochs it fitted, so the
        # intercept follows from the slope without refitting.
        t_bar = t[fit].mean()
        d_bar = rel_mm[fit].mean(axis=0)
        ends = np.array([seg.t_start, seg.t_end])
        line = d_bar[None, :] + np.outer(ends - t_bar, vel)
        span = seg.t_end - seg.t_start
        if span == 0:
            # Every epoch on one day: the slope is lstsq's arbitrary minimum-
            # norm answer and _fit_segment reports sigma 0, i.e. "exact".
            warnings.append(
                f"segment {k} has all {int(members.sum())} epochs at one time: "
                "its velocity and sigma are meaningless"
            )
        segments.append({
            "index": k,
            "t_start": seg.t_start,
            "t_end": seg.t_end,
            "span_yr": float(span),
            "n_epochs": int(members.sum()),
            "n_fit": int(seg.n_points),
            "n_outliers": len(seg.outlier_rows),
            "velocity_mm_yr": _enu(vel),
            "sigma_mm_yr": {"e": seg.sig_ve, "n": seg.sig_vn, "u": seg.sig_vu},
            "r2": {"e": seg.r2_e, "n": seg.r2_n, "u": seg.r2_u},
            "short_span": bool(span < min_span_years),
            "line": {
                "t": [float(x) for x in ends],
                "e_mm": [float(x) for x in line[:, 0]],
                "n_mm": [float(x) for x in line[:, 1]],
                "u_mm": [float(x) for x in line[:, 2]],
            },
        })

    final = segments[-1]
    if final["short_span"]:
        warnings.append(
            f"final segment spans {final['span_yr'] * 365.25:.0f} days "
            f"(< {min_span_years:g} yr): its velocity is not a secular rate"
        )

    return {
        "schema": SCHEMA,
        "station": station,
        "reference": reference,
        "offsets_catalog": offsets_catalog,
        "outlier_rule": {
            "method": "iqr",
            "factor": float(outlier_iqr_factor),
            "scope": "per_segment",
            "on": "raw_values",
            "mode": mode.value,
        },
        "origin_m": _enu(origin),
        "series": {
            "t": [float(x) for x in t],
            "e_mm": [float(x) for x in rel_mm[:, 0]],
            "n_mm": [float(x) for x in rel_mm[:, 1]],
            "u_mm": [float(x) for x in rel_mm[:, 2]],
            "outlier": [bool(x) for x in outlier],
            "in_fit": [bool(x) for x in in_fit],
            "excluded": [bool(x) for x in excluded],
            "segment": segment_idx,
        },
        "offsets": [
            {
                "t": e.date,
                "type": e.offset_type.value,
                "label": _TYPE_LABELS[e.offset_type],
                # The rule estimate_velocity splits on: searchsorted lands
                # strictly inside the series.
                "within_span": bool(t[0] < e.date <= t[-1]),
            }
            for e in events
        ],
        "segments": segments,
        "velocity": {
            "segment": final["index"],
            "velocity_mm_yr": final["velocity_mm_yr"],
            "sigma_mm_yr": final["sigma_mm_yr"],
            "span_yr": final["span_yr"],
            "short_span": final["short_span"],
            "covers_latest_epoch": covers_latest,
        },
        "min_span_years": float(min_span_years),
        "exclusions": {
            "requested": int(np.unique(asked).size),
            "matched": int(np.unique(asked).size) - len(unmatched),
            "unmatched": unmatched,
        },
        "warnings": warnings,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def station_status(
    crd_dir: CrdDirs,
    station: str,
    reference: str,
    *,
    offsets_catalog: str | Path | None = None,
    outlier_mode: OutlierMode | str = OutlierMode.RECORD,
    outlier_iqr_factor: float = 3.0,
    min_span_years: float = MIN_SPAN_YEARS,
    exclude_sessions: list[str] | None = None,
) -> dict[str, Any]:
    """
    Status of one station from daily final CRD files.

    Args:
        crd_dir:          Directory of Bernese `*.CRD` files, one per day, or
                          several directories oldest first, read as one series
                          (see `crd_directory_to_enu`). Epochs in more than one
                          datum add a warning, and so do days the reference's
                          absence removed from the series.
        station:          4-character station code.
        reference:        4-character code of the ENU origin.
        offsets_catalog:  Path to an `offsets` file. Recorded with its sha256,
                          because a velocity is only interpretable alongside
                          the exact catalog that produced it. None fits one
                          segment and says so in `warnings`.
        outlier_mode, outlier_iqr_factor, min_span_years: see `series_status`.
        exclude_sessions: Session dates "YYYY-DDD" of epochs a person confirmed
                          as outliers. Converted with the same rule the CRD
                          files' epochs are (`session_to_decimal_year`), so the
                          match to `series.t` is exact; see `series_status`'s
                          `exclude_epochs`.

    Raises:
        ValueError: no usable CRD files, reference or station not found,
                    station == reference, a malformed catalog, or any
                    `series_status` error.
    """
    code = station.upper()[:4]
    ref = reference.upper()[:4]
    if code == ref:
        raise ValueError(
            f"{code} is the reference station: its series relative to itself "
            "is identically zero"
        )

    epochs = crd_directory_to_enu(crd_dir, ref, station=code)
    if not epochs:
        raise ValueError(
            f"Station {code!r} has no estimated coordinates in {crd_dirs_text(crd_dir)} "
            f"on any day the reference {ref} has"
        )

    t = np.array([ep.decimal_year for ep in epochs])
    enu_m = np.array([[ep.east_m, ep.north_m, ep.up_m] for ep in epochs])

    events: list[OffsetEvent] | None = None
    provenance: dict[str, str] | None = None
    if offsets_catalog is not None:
        path = Path(offsets_catalog)
        before = _sha256(path)
        # The loader keeps the file's case; merge rather than overwrite, so
        # "abcd" and "ABCD" lines both reach the fit (series_status re-sorts).
        catalog: dict[str, list[OffsetEvent]] = {}
        for name, evs in load_offsets_catalog(path).items():
            catalog.setdefault(name.upper(), []).extend(evs)
        events = catalog.get(code, [])
        # The hash is provenance for the events actually fitted: refuse if the
        # file changed between hashing and parsing.
        digest = _sha256(path)
        if digest != before:
            raise ValueError(f"{path} changed while it was being read; try again")
        provenance = {"path": str(path), "sha256": digest}

    result = series_status(
        t, enu_m,
        station=code,
        reference=ref,
        offsets=events,
        outlier_mode=outlier_mode,
        outlier_iqr_factor=outlier_iqr_factor,
        min_span_years=min_span_years,
        offsets_catalog=provenance,
        exclude_epochs=[session_date_to_decimal_year(s) for s in exclude_sessions or []],
    )
    # The first epoch's ENU vector is the straight line from the reference to the
    # station, whatever its axes, and its length gives the arc between them.
    chord = float(np.linalg.norm(enu_m[0]))
    distance = float(np.degrees(2 * np.arcsin(min(1.0, chord / (2 * _EARTH_RADIUS_M)))))
    result["reference_distance_deg"] = distance
    result["reference_warning"] = None
    if distance > REFERENCE_WARN_DEG:
        result["reference_warning"] = (
            f"the reference {ref} is {distance:.1f} degrees from {code}: East, North and Up "
            "are the reference's axes, so a reference this far away rotates the station's "
            "motion between them. Choose a nearer reference to read the components"
        )
        result["warnings"].append(result["reference_warning"])
    missing, days = days_without_station(crd_dir, ref)
    if missing:
        result["warnings"].append(
            f"the reference {ref} is missing from {missing} of {days} daily CRD files: "
            "those days give no epoch for any station"
        )
    datums = crd_datums(crd_dir, epochs=set(t.tolist()))
    if len(datums) > 1:
        spans = "; ".join(
            f"{name} {first:.4f} to {last:.4f}"
            for name, (first, last) in sorted(datums.items(), key=lambda kv: kv[1])
        )
        result["warnings"].append(
            f"the CRD files use more than one geodetic datum ({spans}): "
            "a step where they meet is the frame, not motion"
        )
    return result


def session_date_to_decimal_year(session_date: str) -> float:
    """"YYYY-DDD" -> decimal year, by the same rule the CRD epochs use.

    Goes through `session_to_decimal_year` on the YYDDD code, so the result is
    bit-for-bit the time `crd_directory_to_enu` gives that day's file.
    """
    m = re.fullmatch(r"(\d{4})-(\d{3})", session_date)
    if not m:
        raise ValueError(f"expected a session date YYYY-DDD, got {session_date!r}")
    year, doy = int(m[1]), int(m[2])
    if not 1981 <= year <= 2080:
        raise ValueError(f"{session_date}: the YYDDD rule covers 1981 to 2080 only")
    return session_to_decimal_year(f"{year % 100:02d}{doy:03d}")
