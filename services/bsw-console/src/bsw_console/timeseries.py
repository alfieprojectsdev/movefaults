"""The Time series page (stage 5): pogf_geodetic_suite.timeseries.status, in-process.

Read-only. ``station_status`` reads a directory of daily final CRD files,
builds each station's ENU series relative to a reference station, looks up
its events in the offsets catalog and fits the offset-aware segmented
velocity: the port verified against PHIVOLCS' MATLAB. The console calls it
in this process, never as a subprocess, and adds no arithmetic of its own: what
the page shows is what status returned, velocity and 1-sigma uncertainty,
outlier counts per segment, the catalog's sha256 and the outlier mode.

The outlier mode is status's default, "record": flagged epochs are reported
and kept in the fit. Whether they should be excluded is an open team
decision (docs/SETTLED.md section 6); the page shows the mode, it does not choose one.

The reference station is chosen on the page: every series is relative to it,
and which one is right is a science choice, not a deployment setting. The
page lists every station the CRD files hold as a candidate;
BSW_CONSOLE_TS_REFERENCE, if set, is only the one it starts with.

The CRD directory and the offsets catalog come from settings with no defaults
(settings.py). Until both are set, both endpoints answer 200 with
configured=false and the names of the missing settings. With no reference
chosen and no default, the summary lists the candidates and says to choose
one. A station status cannot compute (not in the files, the reference itself,
a reference the files do not hold, a malformed catalog) is answered with
available=false and the reason.
"""

from __future__ import annotations

from pathlib import Path

from pogf_geodetic_suite.timeseries.crd_pipeline import crd_directory_to_enu, read_crd_file
from pogf_geodetic_suite.timeseries.status import OutlierMode, station_status

from .settings import Settings

SETTINGS = (
    ("BSW_CONSOLE_TS_CRD_DIR", "ts_crd_dir"),
    ("BSW_CONSOLE_TS_OFFSETS", "ts_offsets"),
)
DEFAULT_MODE = OutlierMode.RECORD.value


def _not_configured(s: Settings) -> dict | None:
    missing = [env for env, attr in SETTINGS if not getattr(s, attr)]
    if not missing:
        return None
    return {
        "configured": False,
        "missing": missing,
        "message": "The time series is not configured for this console: set "
        + ", ".join(missing)
        + " (the daily final CRD directory and the offsets catalog).",
    }


def stations_in(crd_dir: Path) -> list[str]:
    """Every estimated station in the directory's CRD files: the reference candidates."""
    codes: set[str] = set()
    files = sorted(crd_dir.glob("*.CRD"))
    for path in files:
        codes.update(code for code, *_ in read_crd_file(path))
    if not codes:
        raise ValueError(f"No usable *.CRD files found in {crd_dir}")
    return sorted(codes)


def _reference(s: Settings, requested: str | None) -> str | None:
    """The page's choice, else the configured default, else None."""
    return (requested or s.ts_reference or "").upper() or None


def _inputs(s: Settings, reference: str | None) -> dict:
    return {
        "crd_dir": str(s.ts_crd_dir),
        "reference": reference,
        "default_reference": s.ts_reference,
        "offsets_path": str(s.ts_offsets),
    }


def summary(s: Settings, reference: str | None = None) -> dict:
    """The reference candidates, the stations relative to the chosen one, and the mode."""
    if (no := _not_configured(s)) is not None:
        return no
    ref = _reference(s, reference)
    try:
        candidates = stations_in(s.ts_crd_dir)  # type: ignore[arg-type]
    except (OSError, ValueError) as exc:
        return {"configured": True, "available": False, **_inputs(s, ref), "message": str(exc)}
    out = {
        "configured": True,
        **_inputs(s, ref),
        "all_stations": candidates,
        "outlier_mode": DEFAULT_MODE,
    }
    if ref is None:
        return {**out, "available": True, "stations": [],
                "message": "Choose a reference station: every series is relative to it."}  # fmt: skip
    if ref not in candidates:
        return {**out, "available": False, "stations": [],
                "message": f"{ref} is not an estimated station in these CRD files."}  # fmt: skip
    try:
        epochs = crd_directory_to_enu(s.ts_crd_dir, ref)  # type: ignore[arg-type]
    except (OSError, ValueError) as exc:
        return {**out, "available": False, "stations": [], "message": str(exc)}
    return {**out, "available": True, "stations": sorted({e.station for e in epochs} - {ref})}


def for_station(s: Settings, code: str, reference: str | None = None) -> dict:
    """What station_status returns for one station, relative to the chosen reference."""
    if (no := _not_configured(s)) is not None:
        return no
    ref = _reference(s, reference)
    base = {"configured": True, **_inputs(s, ref), "station": code.upper()}
    if ref is None:
        return {**base, "available": False, "message": "Choose a reference station first."}
    try:
        result = station_status(
            s.ts_crd_dir,  # type: ignore[arg-type]
            code.upper(),
            ref,
            offsets_catalog=s.ts_offsets,
        )
    except (OSError, ValueError) as exc:
        return {**base, "available": False, "message": str(exc)}
    return {"configured": True, "available": True, **_inputs(s, ref), **result}
