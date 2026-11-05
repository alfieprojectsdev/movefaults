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

Inputs come from three settings with no defaults (settings.py). Until all
three are set, both endpoints answer 200 with configured=false and the names
of the missing settings. A station status cannot compute (not in the files,
the reference itself, a malformed catalog) is answered with available=false
and status's own message.
"""

from __future__ import annotations

from pogf_geodetic_suite.timeseries.crd_pipeline import crd_directory_to_enu
from pogf_geodetic_suite.timeseries.status import OutlierMode, station_status

from .settings import Settings

SETTINGS = (
    ("BSW_CONSOLE_TS_CRD_DIR", "ts_crd_dir"),
    ("BSW_CONSOLE_TS_REFERENCE", "ts_reference"),
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
        + " (the daily final CRD directory, the reference station and the offsets catalog).",
    }


def _inputs(s: Settings) -> dict:
    return {
        "crd_dir": str(s.ts_crd_dir),
        "reference": s.ts_reference,
        "offsets_path": str(s.ts_offsets),
    }


def summary(s: Settings) -> dict:
    """The stations the CRD files hold, the reference excluded, and the mode."""
    if (no := _not_configured(s)) is not None:
        return no
    try:
        epochs = crd_directory_to_enu(s.ts_crd_dir, s.ts_reference)  # type: ignore[arg-type]
    except (OSError, ValueError) as exc:
        return {"configured": True, "available": False, **_inputs(s), "message": str(exc)}
    stations = sorted({e.station for e in epochs} - {s.ts_reference})
    return {
        "configured": True,
        "available": True,
        **_inputs(s),
        "stations": stations,
        "outlier_mode": DEFAULT_MODE,
    }


def for_station(s: Settings, code: str) -> dict:
    """What station_status returns for one station, with its default outlier mode."""
    if (no := _not_configured(s)) is not None:
        return no
    try:
        result = station_status(
            s.ts_crd_dir,  # type: ignore[arg-type]
            code.upper(),
            s.ts_reference,  # type: ignore[arg-type]
            offsets_catalog=s.ts_offsets,
        )
    except (OSError, ValueError) as exc:
        return {
            "configured": True,
            "available": False,
            **_inputs(s),
            "station": code.upper(),
            "message": str(exc),
        }
    return {"configured": True, "available": True, **_inputs(s), **result}
