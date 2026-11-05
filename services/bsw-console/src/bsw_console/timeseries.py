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

The CRDs are read from every yearly result directory the campaign has
(<V_RESULT>/STA for each year, oldest first) as one series, so a velocity comes
from the station's whole history in this campaign and offsets split it where
they fall. The offsets catalog comes
from a setting with no default (settings.py). Until it is set, both endpoints answer 200 with
configured=false and the names of the missing settings. With no reference
chosen and no default, the summary lists the candidates and says to choose
one. A station status cannot compute (not in the files, the reference itself,
a reference the files do not hold, a malformed catalog) is answered with
available=false and the reason.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from pogf_geodetic_suite.timeseries.crd_pipeline import crd_station_codes
from pogf_geodetic_suite.timeseries.status import (
    OutlierMode,
    session_date_to_decimal_year,
    station_status,
)

from . import outliers
from .settings import Campaign, Settings
from .status import campaign_years, year_dir

SETTINGS = (("BSW_CONSOLE_TS_OFFSETS", "ts_offsets"),)
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
        + " (the offsets catalog).",
    }


# Candidates per CRD directory, keyed on what changes when a file is added,
# removed or rewritten: the directory's mtime and each file's name, size and
# mtime. A reference pick then reads the CRDs once (the ENU pass), not twice.
_CANDIDATES: dict[Path, tuple[tuple, list[str]]] = {}


def _fingerprint(crd_dir: Path) -> tuple:
    files = sorted(crd_dir.glob("*.CRD"))
    return (
        crd_dir.stat().st_mtime_ns,
        tuple((f.name, (st := f.stat()).st_size, st.st_mtime_ns) for f in files),
    )


def _stations_in_one(crd_dir: Path) -> list[str]:
    key = _fingerprint(crd_dir)
    hit = _CANDIDATES.get(crd_dir)
    if hit is not None and hit[0] == key:
        return hit[1]
    try:
        codes = crd_station_codes(crd_dir)
    except ValueError:  # a year's folder with no usable file adds nothing
        codes = []
    _CANDIDATES[crd_dir] = (key, codes)
    return codes


def stations_in(dirs: list[Path]) -> list[str]:
    """The reference candidates: exactly what crd_directory_to_enu accepts. The
    stations to plot are these minus the reference, so nothing else needs the
    coordinates read to list them."""
    codes = sorted({code for d in dirs for code in _stations_in_one(d)})
    if not codes:
        raise ValueError("No usable *.CRD files found in " + ", ".join(map(str, dirs)))
    return codes


def _reference(s: Settings, requested: str | None) -> str | None:
    """The page's choice, else the configured default, else None."""
    return (requested or s.ts_reference or "").upper() or None


def crd_dirs(s: Settings, c: Campaign) -> list[Path]:
    """Where the campaign's daily final CRDs are: <V_RESULT>/STA of each year
    that has one, oldest first. A V_RESULT with no year in it gives the same
    folder for every year, which is read once."""
    dirs = [year_dir(s, c.pcf, c.name, y) / "STA" for y in sorted(campaign_years(s, c))]
    return [d for d in dict.fromkeys(dirs) if d.is_dir()]


def _inputs(s: Settings, c: Campaign, reference: str | None) -> dict:
    return {
        "campaign": c.name,
        "crd_dirs": [str(d) for d in crd_dirs(s, c)],
        "reference": reference,
        "default_reference": s.ts_reference,
        "offsets_path": str(s.ts_offsets),
    }


def _missing(s: Settings, c: Campaign) -> str | None:
    if crd_dirs(s, c):
        return None
    return f"No daily final CRDs for {c.name}: none of its years has an STA folder."


def summary(s: Settings, c: Campaign, reference: str | None = None) -> dict:
    """The reference candidates, the stations relative to the chosen one, and the mode."""
    if (no := _not_configured(s)) is not None:
        return no
    ref = _reference(s, reference)
    base = {"configured": True, **_inputs(s, c, ref)}
    if (why := _missing(s, c)) is not None:
        return {**base, "available": False, "stations": [], "message": why}
    try:
        candidates = stations_in(crd_dirs(s, c))
    except (OSError, ValueError) as exc:
        return {**base, "available": False, "message": str(exc)}
    out = {**base, "all_stations": candidates, "outlier_mode": DEFAULT_MODE}
    if ref is None:
        return {**out, "available": True, "stations": [],
                "message": "Choose a reference station: every series is relative to it."}  # fmt: skip
    if ref not in candidates:
        return {**out, "available": False, "stations": [],
                "message": f"{ref} is not an estimated station in these CRD files."}  # fmt: skip
    return {**out, "available": True, "stations": [x for x in candidates if x != ref]}


def for_station(s: Settings, c: Campaign, code: str, reference: str | None = None) -> dict:
    """What station_status returns for one station, relative to the chosen reference."""
    if (no := _not_configured(s)) is not None:
        return no
    ref = _reference(s, reference)
    base = {"configured": True, **_inputs(s, c, ref), "station": code.upper()}
    if ref is None:
        return {**base, "available": False, "message": "Choose a reference station first."}
    if (why := _missing(s, c)) is not None:
        return {**base, "available": False, "message": why}
    dirs = crd_dirs(s, c)
    try:
        result = station_status(
            dirs,
            code.upper(),
            ref,
            offsets_catalog=s.ts_offsets,
        )
    except (OSError, ValueError) as exc:
        return {**base, "available": False, "message": str(exc)}
    out = {"configured": True, "available": True, **_inputs(s, c, ref), **result}
    decisions = outliers.current(s, c, code.upper(), dirs, ref)
    out["decisions"] = decisions
    out["decided_fit"] = None
    leave_out = outliers.excluded_sessions(decisions)
    if leave_out:
        # The same fit with the epochs a person confirmed as outliers left out:
        # shown beside the published one, never instead of it (SETTLED.md
        # section 6 is open). station_status takes them as session dates.
        try:
            alt = station_status(
                dirs, code.upper(), ref,
                offsets_catalog=s.ts_offsets, exclude_sessions=leave_out,
            )  # fmt: skip
        except (OSError, ValueError) as exc:
            out["decided_fit"] = {"available": False, "message": str(exc), "excluded": leave_out}
        else:
            out["decided_fit"] = {
                "available": True,
                "excluded": leave_out,
                "velocity": alt["velocity"],
                "segments": [
                    {k: seg[k] for k in ("index", "n_fit", "velocity_mm_yr", "sigma_mm_yr", "line")}
                    for seg in alt["segments"]
                ],
            }
    return out


def epoch_flag(s: Settings, c: Campaign, station: str, reference: str, epoch: str) -> bool:
    """Whether the rule flags `epoch` of `station` relative to `reference`, as
    the page shows it. 404 when the station has no epoch on that date."""
    if (no := _not_configured(s)) is not None:
        raise HTTPException(409, no["message"])
    try:
        t_epoch = session_date_to_decimal_year(epoch)
        result = station_status(
            crd_dirs(s, c), station, reference, offsets_catalog=s.ts_offsets
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None
    hits = [i for i, t in enumerate(result["series"]["t"]) if t == t_epoch]
    if not hits:
        raise HTTPException(404, f"{station} has no epoch on {epoch} relative to {reference}")
    return any(result["series"]["outlier"][i] for i in hits)
