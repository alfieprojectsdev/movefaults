"""
GMT-format output for velocity fields.

WHY THIS EXISTS
Requested by PHIVOLCS (Cass, 2026-08-13) as item 4 of the stage 3 wishlist:
"Mapping of velocity vectors / generating input files for GMT or GMT-formatted
files". It is the smallest item on that list with no external dependency, and
it produces the first artefact of this pipeline that the group can look at
rather than read -- which also makes it the cheapest check that the ported
velocity estimation gives numbers people recognise.

THE FORMAT
`psvelo -Se` (GMT 4/5) and `velo -Se` (GMT 6) both consume:

    lon  lat  Ve  Vn  sigma_Ve  sigma_Vn  correlation_EN  [name]

Velocities and sigmas in the same unit, conventionally mm/yr for GNSS. The
`-Se<scale>/<confidence>/<fontsize>` argument sets the arrow scale and the
confidence level of the error ellipse.

THE THING THAT MAKES A VELOCITY MAP WRONG
**These velocities are relative to a reference station, not absolute.** The ENU
pipeline transforms every site into a local frame anchored on one site (S01R
historically, PIMO under discussion), so a vector on the resulting map reads
"motion with respect to that site", not "motion in ITRF". Change the reference
and every arrow changes.

A GMT file is just numbers; nothing in the format records this. A map made from
one and captioned "PH GNSS velocities" is actively misleading -- and once it is
a PNG in a presentation, the frame is unrecoverable. So every writer here emits
the reference station and the epoch span as `#` comment lines, which GMT
ignores and a human does not. **Do not strip them to make the file tidy.**

ON THE CORRELATION COLUMN
It is written as 0.0, and that is an honest value rather than a placeholder.
`estimate_velocity` and `estimate_velocity_joint` solve East and North as
separate least-squares problems sharing one design matrix, so under that model
their formal errors are uncorrelated by construction. A real E/N correlation
would have to be propagated from the daily solution covariance -- which the
SINEX files do carry and this pipeline does not currently read. Writing a
fabricated nonzero value would put a shape on the error ellipse that no
computation supports.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..modeling.coordinates import ecef_to_geodetic
from .analysis import JointVelocityResult, VelocityResult
from .crd_pipeline import read_crd_file


@dataclass(frozen=True)
class VelocityVector:
    """One station's horizontal velocity, positioned for mapping."""
    station: str
    lon_deg: float
    lat_deg: float
    ve_mm_yr: float
    vn_mm_yr: float
    sig_ve: float
    sig_vn: float
    vu_mm_yr: float | None = None
    sig_vu: float | None = None
    corr_en: float = 0.0

    @property
    def speed_mm_yr(self) -> float:
        return (self.ve_mm_yr ** 2 + self.vn_mm_yr ** 2) ** 0.5


def station_positions(crd_path: Path) -> dict[str, tuple[float, float, float]]:
    """
    Read station positions from one Bernese CRD file as (lon, lat, height).

    Any epoch's CRD serves: a few centimetres of inter-epoch motion is invisible
    at map scale, and using a single file keeps the positions self-consistent.
    """
    out: dict[str, tuple[float, float, float]] = {}
    for station, x, y, z in read_crd_file(crd_path):
        lat, lon, alt = ecef_to_geodetic(x, y, z)
        out[station.upper()] = (lon, lat, alt)
    return out


def to_vectors(
    results: Iterable[VelocityResult | JointVelocityResult],
    positions: Mapping[str, tuple[float, float, float]],
    *,
    skip_missing: bool = True,
) -> tuple[list[VelocityVector], list[str]]:
    """
    Pair velocity results with positions.

    Accepts either result type. For a `VelocityResult` the LAST segment is used,
    matching what the MATLAB publishes -- see the warning in `write_psvelo`
    about short final segments. For a `JointVelocityResult` the rate in force at
    the end of the record is used, via `rate_at`, so a fitted rate change is
    respected.

    Returns:
        (vectors, skipped) -- `skipped` names stations with no position, so a
        silently short map is not possible.
    """
    vectors: list[VelocityVector] = []
    skipped: list[str] = []

    for r in results:
        pos = positions.get(r.station.upper())
        if pos is None:
            skipped.append(r.station)
            if skip_missing:
                continue
            raise KeyError(f"No position for station {r.station!r}")
        lon, lat, _ = pos

        if isinstance(r, JointVelocityResult):
            ve, vn, vu = r.rate_at(r.t_end)
            sig_ve, sig_vn, sig_vu = r.sig_ve, r.sig_vn, r.sig_vu
        else:
            seg = r.final_velocity
            ve, vn, vu = seg.ve_mm_yr, seg.vn_mm_yr, seg.vu_mm_yr
            sig_ve, sig_vn, sig_vu = seg.sig_ve, seg.sig_vn, seg.sig_vu

        vectors.append(
            VelocityVector(
                station=r.station.upper(), lon_deg=lon, lat_deg=lat,
                ve_mm_yr=ve, vn_mm_yr=vn, sig_ve=sig_ve, sig_vn=sig_vn,
                vu_mm_yr=vu, sig_vu=sig_vu,
            )
        )

    return vectors, skipped


def _header(reference_station: str, extra: Iterable[str] = ()) -> list[str]:
    lines = [
        "# GNSS velocity field — GMT psvelo/velo -Se format",
        f"# generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "#",
        f"# REFERENCE FRAME: velocities are RELATIVE TO STATION {reference_station}.",
        "# They are not ITRF velocities. A map made from this file must say so;",
        "# change the reference station and every vector changes.",
        "#",
    ]
    lines.extend(f"# {line}" for line in extra)
    return lines


def write_psvelo(
    vectors: Iterable[VelocityVector],
    path: Path,
    *,
    reference_station: str,
    max_speed_mm_yr: float | None = 200.0,
    withhold: Mapping[str, str] | None = None,
    notes: Iterable[str] = (),
) -> tuple[int, list[str]]:
    """
    Write a horizontal velocity field in `psvelo -Se` format.

    Args:
        vectors:            What to write.
        path:               Output file.
        reference_station:  Recorded in the header. Required, not optional --
                            see the module docstring.
        max_speed_mm_yr:    Stations faster than this are written as commented
                            lines rather than dropped. Default 200 mm/yr is far
                            above any real PH rate (~40 mm/yr) and exists to
                            catch the short-final-segment defect: ALBU's
                            published East rate was -539 mm/yr and TARL's 2008
                            mm/yr, both artefacts of fitting days of data. A
                            map drawn with those in it is unreadable, because
                            GMT scales the arrows to the largest vector. Pass
                            None to disable.
        withhold:           {station: reason} the CALLER wants held back, e.g.
                            a final interval too short to carry a rate. The
                            speed threshold alone does not catch these: LUZD's
                            -115 mm/yr is implausible for the Philippines but
                            passes a 200 mm/yr filter, and it comes from 36 days
                            of data. Without this, a station the pipeline has
                            already flagged as "not a velocity" still gets drawn.
        notes:              Extra `#` header lines, e.g. the epoch span.

    Returns:
        (n_written, quarantined) -- station names moved to comments, from both
        the speed threshold and `withhold`.
    """
    vectors = list(vectors)
    lines = _header(reference_station, notes)
    lines.append("# lon  lat  Ve  Vn  sigVe  sigVn  corrEN  station   (mm/yr)")

    withhold = {k.upper(): v for k, v in (withhold or {}).items()}
    quarantined: list[str] = []
    body: list[str] = []
    for v in sorted(vectors, key=lambda x: x.station):
        row = (f"{v.lon_deg:11.6f} {v.lat_deg:11.6f} "
               f"{v.ve_mm_yr:9.3f} {v.vn_mm_yr:9.3f} "
               f"{v.sig_ve:7.3f} {v.sig_vn:7.3f} {v.corr_en:6.3f} {v.station}")
        reason = withhold.get(v.station)
        if reason is None and max_speed_mm_yr is not None \
                and v.speed_mm_yr > max_speed_mm_yr:
            reason = f"{v.speed_mm_yr:.0f} mm/yr exceeds {max_speed_mm_yr:g}"
        if reason:
            quarantined.append(v.station)
            body.append(f"# WITHHELD ({reason}) {row}")
        else:
            body.append(row)

    if quarantined:
        lines.append(f"# {len(quarantined)} station(s) WITHHELD — written as comments")
        lines.append("# below, with the reason. Nothing has been deleted: uncomment a")
        lines.append("# row to reinstate it. Review before drawing the map.")
        lines.append(f"# withheld: {' '.join(quarantined)}")

    path.write_text("\n".join(lines + body) + "\n", encoding="utf-8")
    return len(vectors) - len(quarantined), quarantined


def write_vertical(
    vectors: Iterable[VelocityVector],
    path: Path,
    *,
    reference_station: str,
    notes: Iterable[str] = (),
) -> int:
    """
    Write vertical rates as `lon lat Vu sigVu station`, for plotting with
    `psxy -Sc` sized by rate or coloured through a CPT.

    Vertical is separated from the horizontal file on purpose. It is the noisier
    component by roughly a factor of three (measured: median daily repeatability
    N 2.8 / E 3.0 / U 10.9 mm), and putting it on the same map as the horizontal
    field invites reading the two at the same confidence.
    """
    lines = _header(reference_station, notes)
    lines.append("# lon  lat  Vu  sigVu  station   (mm/yr, positive up)")
    n = 0
    for v in sorted(vectors, key=lambda x: x.station):
        if v.vu_mm_yr is None:
            continue
        lines.append(f"{v.lon_deg:11.6f} {v.lat_deg:11.6f} "
                     f"{v.vu_mm_yr:9.3f} {(v.sig_vu or 0.0):7.3f} {v.station}")
        n += 1
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n
