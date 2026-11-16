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

import csv
import io
import tempfile
from pathlib import Path

from fastapi import HTTPException
from pogf_geodetic_suite.timeseries.crd_pipeline import crd_station_xyz
from pogf_geodetic_suite.timeseries.gmt import VelocityVector, write_psvelo, write_vertical
from pogf_geodetic_suite.timeseries.status import (
    OutlierMode,
    field_status,
    session_date_to_decimal_year,
    station_positions,
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


# Each station's position per CRD directory, which is also the candidate list,
# keyed on what changes when a file is added, removed or rewritten: the directory's
# mtime and each file's name, size and mtime. A reference pick then reads the CRDs
# once (the ENU pass), not twice.
_XYZ: dict[Path, tuple[tuple, dict[str, tuple[float, float, float]]]] = {}


def _fingerprint(crd_dir: Path) -> tuple:
    files = sorted(crd_dir.glob("*.CRD"))
    return (
        crd_dir.stat().st_mtime_ns,
        tuple((f.name, (st := f.stat()).st_size, st.st_mtime_ns) for f in files),
    )


def _xyz_in_one(crd_dir: Path) -> dict[str, tuple[float, float, float]]:
    key = _fingerprint(crd_dir)
    hit = _XYZ.get(crd_dir)
    if hit is not None and hit[0] == key:
        return hit[1]
    try:
        xyz = crd_station_xyz(crd_dir)
    except ValueError:  # a year's folder with no usable file adds nothing
        xyz = {}
    _XYZ[crd_dir] = (key, xyz)
    return xyz


def _xyz_in(dirs: list[Path]) -> dict[str, tuple[float, float, float]]:
    """Each station's newest position: `dirs` run oldest first, so later years win."""
    xyz: dict[str, tuple[float, float, float]] = {}
    for d in dirs:
        xyz.update(_xyz_in_one(d))
    if not xyz:
        raise ValueError("No usable *.CRD files found in " + ", ".join(map(str, dirs)))
    return xyz


def stations_in(dirs: list[Path]) -> list[str]:
    """The reference candidates: exactly what crd_directory_to_enu accepts. The
    stations to plot are these minus the reference, so nothing else needs the
    coordinates read to list them."""
    return sorted(_xyz_in(dirs))


def _reference(s: Settings, requested: str | None) -> str | None:
    """The page's choice, else the configured default, else None."""
    return (requested or s.ts_reference or "").upper() or None


def crd_dirs(s: Settings, c: Campaign) -> list[Path]:
    """Where the campaign's daily final CRDs are: <V_RESULT>/STA of each year
    that has one, oldest first. A V_RESULT with no year in it gives the same
    folder for every year, which is read once."""
    dirs = [year_dir(s, c.pcf, c.name, y) / "STA" for y in sorted(campaign_years(s, c))]
    return [d for d in dict.fromkeys(dirs) if d.is_dir()]


def _inputs(s: Settings, c: Campaign, dirs: list[Path], reference: str | None) -> dict:
    return {
        "campaign": c.name,
        "crd_dirs": [str(d) for d in dirs],
        "reference": reference,
        "default_reference": s.ts_reference,
        "offsets_path": str(s.ts_offsets),
    }


def _no_dirs(c: Campaign) -> str:
    return f"No daily final CRDs for {c.name}: none of its years has an STA folder."


def summary(s: Settings, c: Campaign, reference: str | None = None) -> dict:
    """The reference candidates, the stations relative to the chosen one, and the mode."""
    if (no := _not_configured(s)) is not None:
        return no
    ref = _reference(s, reference)
    dirs = crd_dirs(s, c)
    base = {"configured": True, **_inputs(s, c, dirs, ref)}
    if not dirs:
        return {**base, "available": False, "stations": [], "message": _no_dirs(c)}
    try:
        xyz = _xyz_in(dirs)
    except (OSError, ValueError) as exc:
        return {**base, "available": False, "message": str(exc)}
    candidates = sorted(xyz)
    out = {
        **base,
        "all_stations": candidates,
        "outlier_mode": DEFAULT_MODE,
        **station_positions(xyz, ref),
    }
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
    dirs = crd_dirs(s, c)
    base = {"configured": True, **_inputs(s, c, dirs, ref), "station": code.upper()}
    if ref is None:
        return {**base, "available": False, "message": "Choose a reference station first."}
    if not dirs:
        return {**base, "available": False, "message": _no_dirs(c)}
    try:
        result = station_status(
            dirs,
            code.upper(),
            ref,
            offsets_catalog=s.ts_offsets,
        )
    except (OSError, ValueError) as exc:
        return {**base, "available": False, "message": str(exc)}
    out = {**base, "available": True, **result}
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


# The whole field per campaign and reference, kept until a CRD file or the
# catalog changes. About 0.1 s a station to compute, so it is done on request
# and remembered, not queued (velocity_map_design.md).
_FIELD: dict[tuple[str, str], tuple[tuple, dict]] = {}


def field(s: Settings, c: Campaign, reference: str | None = None) -> dict:
    """Every station's velocity relative to the chosen reference: field_status,
    with the same answers as `summary` when it can't."""
    if (no := _not_configured(s)) is not None:
        return no
    ref = _reference(s, reference)
    dirs = crd_dirs(s, c)
    base = {"configured": True, **_inputs(s, c, dirs, ref)}
    if ref is None:
        return {**base, "available": False, "message": "Choose a reference station first."}
    if not dirs:
        return {**base, "available": False, "message": _no_dirs(c)}
    try:
        st = s.ts_offsets.stat()
        key = (tuple(_fingerprint(d) for d in dirs), str(s.ts_offsets), st.st_size, st.st_mtime_ns)
        hit = _FIELD.get((c.name, ref))
        if hit is None or hit[0] != key:
            hit = (key, field_status(dirs, ref, offsets_catalog=s.ts_offsets))
            _FIELD[(c.name, ref)] = hit
    except (OSError, ValueError) as exc:
        return {**base, "available": False, "message": str(exc)}
    return {**base, "available": True, **hit[1]}


EXPORTS = ("psvelo", "vertical", "csv")


def _withheld(entry: dict) -> str | None:
    """Why a station's rate should not be drawn as a velocity, if it shouldn't."""
    v = entry["velocity"]
    if v["short_span"]:
        return f"final segment spans {v['span_yr']:.2f} yr, under the minimum"
    if not v["covers_latest_epoch"]:
        return "the newest epochs are too few to fit: this is the rate before the latest event"
    return None


def field_export(s: Settings, c: Campaign, reference: str | None, kind: str) -> tuple[str, str]:
    """(file name, text) of the field as a GMT psvelo file, a vertical-rate file
    or a CSV table. The GMT files are timeseries.gmt's own, so a figure made from
    them shows what the page shows. A station whose rate is not a velocity (short
    or stale final segment) is written as a comment with the reason, not dropped."""
    if kind not in EXPORTS:
        raise HTTPException(422, "format is one of: " + ", ".join(EXPORTS))
    f = field(s, c, reference)
    if not f.get("configured") or not f.get("available"):
        raise HTTPException(409, f.get("message", "the velocity field is not available"))
    ref = f["reference"]
    notes = [
        f"campaign: {c.name}",
        f"epoch span: {f['t_first']:.4f} to {f['t_last']:.4f}",
        f"offsets catalog sha256: {f['offsets_catalog']['sha256']}",
        f"outlier mode: {f['outlier_rule']['mode']}",
        f"sigma: {f['sigma']}",
    ]
    name = f"{c.name}_velocity_relative_to_{ref}"
    if kind == "csv":
        out = io.StringIO()
        for line in [f"velocities relative to station {ref}; not ITRF velocities", *notes]:
            out.write(f"# {line}\n")
        w = csv.writer(out, lineterminator="\n")
        w.writerow(["station", "lon", "lat", "ve_mm_yr", "vn_mm_yr", "vu_mm_yr",
                    "sig_ve", "sig_vn", "sig_vu", "span_yr", "n_epochs",
                    "short_span", "covers_latest_epoch", "reference_distance_deg",
                    "far_from_reference"])  # fmt: skip
        for e in f["stations"]:
            v, sg = e["velocity"]["velocity_mm_yr"], e["velocity"]["sigma_mm_yr"]
            w.writerow([e["station"], f"{e['lon']:.6f}", f"{e['lat']:.6f}",
                        f"{v['e']:.3f}", f"{v['n']:.3f}", f"{v['u']:.3f}",
                        f"{sg['e']:.3f}", f"{sg['n']:.3f}", f"{sg['u']:.3f}",
                        f"{e['velocity']['span_yr']:.3f}", e["n_epochs"],
                        e["velocity"]["short_span"], e["velocity"]["covers_latest_epoch"],
                        f"{e['reference_distance_deg']:.2f}", e["far_from_reference"]])  # fmt: skip
        return name + ".csv", out.getvalue()
    vectors = [
        VelocityVector(
            station=e["station"], lon_deg=e["lon"], lat_deg=e["lat"],
            ve_mm_yr=e["velocity"]["velocity_mm_yr"]["e"],
            vn_mm_yr=e["velocity"]["velocity_mm_yr"]["n"],
            sig_ve=e["velocity"]["sigma_mm_yr"]["e"],
            sig_vn=e["velocity"]["sigma_mm_yr"]["n"],
            vu_mm_yr=e["velocity"]["velocity_mm_yr"]["u"],
            sig_vu=e["velocity"]["sigma_mm_yr"]["u"],
            final_span_yr=e["velocity"]["span_yr"],
        )
        for e in f["stations"]
    ]  # fmt: skip
    withhold = {e["station"]: why for e in f["stations"] if (why := _withheld(e))}
    write = write_psvelo if kind == "psvelo" else write_vertical
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "field"
        write(vectors, path, reference_station=ref, withhold=withhold, notes=notes)
        text = path.read_text(encoding="utf-8")
    return name + (".psvelo" if kind == "psvelo" else "_vertical.txt"), text


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
