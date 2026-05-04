"""
Bernese 5.4 campaign file generators.

Each function returns the file content as a string.  The callers are
responsible for writing to the correct path (STA/, CRD/ etc.).

File format references: GPSDATA/CAMPAIGN54/EXAMPLE/STA/ on the T420 install.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

import pymap3d

from .campaign_models import StationRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.utcnow().strftime("%d-%b-%y %H:%M").upper()


def _date_field(dt: datetime | None) -> str:
    """Format a datetime as Bernese 'YYYY MM DD HH MM SS' (19 chars)."""
    if dt is None:
        return " " * 19
    return f"{dt.year:4d} {dt.month:2d} {dt.day:2d} {dt.hour:2d} {dt.minute:2d} {dt.second:2d}"


def _sta_name(rec: StationRecord) -> str:
    """14-char Bernese station name: '4CODE DDDDDMXXX' padded to 16."""
    raw = f"{rec.name[:4]} {rec.dome}"
    return f"{raw:<16}"


# ---------------------------------------------------------------------------
# STA file
# ---------------------------------------------------------------------------

_STA_HEADER = """\
{title:<64} {date}
--------------------------------------------------------------------------------

FORMAT VERSION: 1.03
TECHNIQUE:      GNSS

TYPE 001: RENAMING OF STATIONS
------------------------------

STATION NAME          FLG          FROM                   TO         OLD STATION NAME      REMARK
****************      ***  YYYY MM DD HH MM SS  YYYY MM DD HH MM SS  ********************  ************************
"""

_STA_TYPE002_HEADER = """
TYPE 002: STATION INFORMATION
-----------------------------

STATION NAME          FLG          FROM                   TO         RECEIVER TYPE         RECEIVER SERIAL NBR   REC #   ANTENNA TYPE          ANTENNA SERIAL NBR    ANT #    NORTH      EAST      UP     AZIMUTH  LONG NAME  DESCRIPTION             REMARK
****************      ***  YYYY MM DD HH MM SS  YYYY MM DD HH MM SS  ********************  ********************  ******  ********************  ********************  ******  ***.****  ***.****  ***.****  ******  *********  **********************  ************************
"""


def generate_sta(stations: list[StationRecord], title: str = "PHIVOLCS CORS NETWORK") -> str:
    """Generate Bernese 5.4 STA (station information) file content."""
    lines: list[str] = []
    lines.append(_STA_HEADER.format(title=title, date=_now_str()))

    for rec in stations:
        sname = _sta_name(rec)
        from_s = _date_field(rec.start)
        to_s = _date_field(rec.end)
        old_name = f"{rec.name[:4]}*"
        lines.append(f"{sname}      001  {from_s}  {to_s}  {old_name:<20}  PHIVOLCS")

    lines.append(_STA_TYPE002_HEADER)

    for rec in stations:
        sname = _sta_name(rec)
        from_s = _date_field(rec.start)
        to_s = _date_field(rec.end)
        receiver = f"{rec.receiver:<20}"
        rec_serial = " " * 20
        antenna = f"{rec.antenna:<20}"
        ant_serial = f"{rec.antenna_serial:<20}"
        long_name = f"{rec.name[:4]}00PHL"
        lines.append(
            f"{sname}      001  {from_s}  {to_s}  {receiver}  {rec_serial}  999999  "
            f"{antenna}  {ant_serial}  999999    0.0000    0.0000    0.0000          "
            f"{long_name:<9}  PHIVOLCS CORS              "
        )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CRD file
# ---------------------------------------------------------------------------

_CRD_HEADER = """\
{title:<64} {date}
--------------------------------------------------------------------------------
LOCAL GEODETIC DATUM: {ref_frame:<20}  EPOCH: {epoch}

 NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG     SYSTEM

"""


def generate_crd(
    stations: list[StationRecord],
    title: str = "PHIVOLCS CORS NETWORK",
    ref_frame: str = "IGS14",
    epoch: str = "2015-01-01 00:00:00",
) -> str:
    """Generate Bernese 5.4 CRD coordinate file content."""
    lines: list[str] = [_CRD_HEADER.format(
        title=title, date=_now_str(), ref_frame=ref_frame, epoch=epoch,
    )]
    for i, rec in enumerate(stations, start=1):
        sname = _sta_name(rec).rstrip()
        lines.append(f"  {i:3d}  {sname:<14}  {rec.x:>15.5f} {rec.y:>15.5f}  {rec.z:>15.5f}    {ref_frame[:5]}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# ABB file
# ---------------------------------------------------------------------------

_ABB_HEADER = """\
{title:<64} {date}
--------------------------------------------------------------------------------

Station name             4-ID    2-ID    Remark
****************         ****     **     ***************************************
"""


def generate_abb(stations: list[StationRecord], title: str = "PHIVOLCS CORS NETWORK") -> str:
    """Generate Bernese 5.4 ABB abbreviations file content."""
    lines: list[str] = [_ABB_HEADER.format(title=title, date=_now_str())]
    for rec in stations:
        sname = _sta_name(rec).rstrip()
        id4 = rec.name[:4].upper()
        id2 = rec.name[:2].upper()
        lines.append(f"{sname:<24}   {id4:4}     {id2:2}     PHIVOLCS CORS")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# VEL file
# ---------------------------------------------------------------------------

_VEL_HEADER = """\
{title:<64} {date}
--------------------------------------------------------------------------------
LOCAL GEODETIC DATUM: {ref_frame:<20}

 NUM  STATION NAME           VX (M/Y)       VY (M/Y)       VZ (M/Y)  FLAG   PLATE

"""


def generate_vel(
    stations: list[StationRecord],
    title: str = "PHIVOLCS CORS NETWORK",
    ref_frame: str = "IGS14",
) -> str:
    """Generate Bernese 5.4 VEL velocity file content."""
    lines: list[str] = [_VEL_HEADER.format(title=title, date=_now_str(), ref_frame=ref_frame)]
    for i, rec in enumerate(stations, start=1):
        sname = _sta_name(rec).rstrip()
        lines.append(f"  {i:3d}  {sname:<14}  {rec.vx:>14.5f} {rec.vy:>14.5f}  {rec.vz:>14.5f}    {ref_frame[:5]}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLU file
# ---------------------------------------------------------------------------

_CLU_HEADER = """\
{title:<64} {date}
--------------------------------------------------------------------------------

STATION NAME      CLU
****************  ***
"""


def generate_clu(stations: list[StationRecord], title: str = "PHIVOLCS CORS NETWORK") -> str:
    """Generate Bernese 5.4 CLU cluster file (all stations assigned to CPU 1)."""
    lines: list[str] = [_CLU_HEADER.format(title=title, date=_now_str())]
    for rec in stations:
        sname = _sta_name(rec).rstrip()
        lines.append(f"{sname:<18}  1")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# BLQ download (Chalmers OTLP)
# ---------------------------------------------------------------------------

_CHALMERS_URL = "https://holt.oso.chalmers.se/loading/"


def download_blq(
    stations: list[StationRecord],
    dest: Path,
    model: str = "FES2014b",
    timeout: int = 120,
) -> None:
    """
    Download ocean loading BLQ from the Chalmers OTLP web service.

    Coordinates are converted from ECEF to geodetic (lon, lat) for the POST
    request.  The response is written directly to *dest* as a Bernese BLQ.

    Raises requests.HTTPError or OSError on network/IO failure.
    """
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests is required for BLQ download (uv add requests)") from exc

    # Build station list in Chalmers lon/lat format
    coord_lines: list[str] = []
    for rec in stations:
        lat, lon, _ = pymap3d.ecef2geodetic(rec.x, rec.y, rec.z, deg=True)
        coord_lines.append(f"{rec.name}  {lon:.4f}  {lat:.4f}")

    station_text = "\n".join(coord_lines) + "\n"

    logger.info("Downloading BLQ for %d stations from Chalmers (model=%s)", len(stations), model)

    resp = requests.post(
        _CHALMERS_URL,
        data={
            "Oload": model,
            "CMC": "off",
            "coordtype": "lonlat",
            "format": "bern54",
        },
        files={"inputfile": ("stations.txt", station_text.encode())},
        timeout=timeout,
    )
    resp.raise_for_status()

    dest.write_text(resp.text, encoding="ascii")
    logger.info("BLQ written to %s", dest)


# ---------------------------------------------------------------------------
# ATX staging
# ---------------------------------------------------------------------------

def stage_atx(atx_source: Path, campaign_atm_dir: Path) -> Path:
    """Copy the ATX antenna file into the campaign's ATM/ directory."""
    campaign_atm_dir.mkdir(parents=True, exist_ok=True)
    dest = campaign_atm_dir / atx_source.name
    if not dest.exists():
        shutil.copy2(atx_source, dest)
        logger.info("Staged ATX: %s → %s", atx_source, dest)
    return dest


# ---------------------------------------------------------------------------
# IGS product pre-download
# ---------------------------------------------------------------------------

def prefetch_igs_products(
    campaign_orb_dir: Path,
    year: int,
    doy: int,
    ac: str = "COD",
) -> None:
    """
    Pre-download IGS SP3 + CLK products for the given date into *campaign_orb_dir*.

    This bypasses BPE step 000 (FTP_DWLD) so the network dependency is
    isolated and reproducible.  Raises if download fails.
    """
    from datetime import datetime

    from pogf_geodetic_suite.igs_downloader import ProductDownloader

    campaign_orb_dir.mkdir(parents=True, exist_ok=True)
    date = datetime(year, 1, 1) + __import__("datetime").timedelta(days=doy - 1)

    dl = ProductDownloader(base_dir=str(campaign_orb_dir))
    for content in ("ORB", "CLK"):
        path = dl.download_product(date, ac=ac, content=content)
        if path is None:
            raise RuntimeError(
                f"IGS {content} download failed for {date.strftime('%Y-%j')} (AC={ac})"
            )
        logger.info("IGS %s: %s", content, path)
