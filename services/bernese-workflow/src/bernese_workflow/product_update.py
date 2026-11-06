"""Fetch new CODE products from cron, and report which Bernese files have gone stale.

WHAT IT FETCHES, AND WHAT IT ONLY REPORTS
Orbits, clocks, ERP, biases and ionosphere maps are fetched: a run needs them, and
adding a file can't change a day already solved. Files are named per day, so an
existing one is never replaced.

CONFIG and REF files (satellite tables, antenna models, fiducial lists) are only
compared with AIUB's, never replaced. These apply to days already solved, so updating
one changes results. A person decides that, as `docs/SETTLED.md` §2 shows: replacing
the binaries on 2026-09-02 moved one station by 40.5 mm on one day.

WHAT COUNTS AS A PROBLEM
A 404 for a recent day isn't a problem: final products appear about a week or two after
the day. A file missing after ``late_days`` is, and so is any other failed download.
Each file must decompress before it's kept, because the mirror can serve a partial file
with a success status, and a truncated orbit file would only fail inside a BPE later.

The outcome goes to <worker state>/products/status.json, which bernese-notify reads, so
a failure reaches the maintainer. fetch_igs_products.sh stays for a manual range, and
also fetches the IGS cross-check files, which no run reads.

    bernese-update-products                     # nightly, from cron
    bernese-update-products --since 2026-04-01  # fill an older gap, once
    bernese-update-products --dry-run           # what it would fetch; writes nothing
"""

from __future__ import annotations

import argparse
import collections.abc
import datetime as dt
import email.utils
import gzip
import os
import sys
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from .run_queue import default_state_dir, now_utc, write_json_atomic

MIRROR = "https://zhw-b.s3.cloud.switch.ch/aiub"
LOOKBACK_DAYS = 60
LATE_DAYS = 21
TIMEOUT_S = 120

# label, folder under $D, file name. The one list: the console's Plan page reads it too.
PRODUCTS = [
    ("orbits", "COD0OPSFIN", "COD0OPSFIN_{y}{d}0000_01D_05M_ORB.SP3.gz"),
    ("clocks", "COD0OPSFIN", "COD0OPSFIN_{y}{d}0000_01D_30S_CLK.CLK.gz"),
    ("ERP", "COD0OPSFIN", "COD0OPSFIN_{y}{d}0000_01D_01D_ERP.ERP.gz"),
    ("DCB/OSB", "COD0OPSFIN", "COD0OPSFIN_{y}{d}0000_01D_01D_OSB.BIA.gz"),
    ("ionosphere", "BSW54", "COD0OPSFIN_{y}{d}0000_01D_01H_GIM.ION.gz"),
]

# Compared, never replaced. Mirror folder under BSWUSER54, the variable holding the local
# folder, and the file. {y} is this year. These are what a run reads: ${CONFIG} and V_REFDIR.
WATCHED = [
    ("CONFIG", "CONFIG", "SAT_{y}.CRX"),
    ("CONFIG", "CONFIG", "SATELLIT_I20.SAT"),
    ("CONFIG", "CONFIG", "SAT_GNSS.CRX"),
    ("CONFIG", "CONFIG", "DATUM.BSW"),
    ("CONFIG", "CONFIG", "GPSUTC.BSW"),
    ("CONFIG", "CONFIG", "FREQINFO.FRQ"),
    ("REF", "REF", "ANTENNA_I20.PCV"),
    ("REF", "REF", "IGS20.FIX"),
    ("REF", "REF", "IGS20_R.CRD"),
    ("REF", "REF", "IGS20_R.VEL"),
    ("REF", "REF", "IGS20.PSD"),
]


class NotPublished(Exception):
    """The mirror has no such file (yet)."""


def _url_open(url: str, method: str = "GET"):
    request = urllib.request.Request(url, method=method)
    try:
        return urllib.request.urlopen(request, timeout=TIMEOUT_S)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotPublished(url) from exc
        raise


def http_get(url: str) -> bytes:
    with _url_open(url) as response:
        return response.read()


def http_head(url: str) -> tuple[int, float | None]:
    """Size and last-modified time of a file on the mirror."""
    with _url_open(url, "HEAD") as response:
        modified = response.headers.get("Last-Modified")
        when = email.utils.parsedate_to_datetime(modified).timestamp() if modified else None
        return int(response.headers.get("Content-Length", -1)), when


def day_name(day: dt.date) -> tuple[str, str]:
    return str(day.year), f"{day.timetuple().tm_yday:03d}"


@dataclass
class Result:
    fetched: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    late: list[str] = field(default_factory=list)
    waiting: int = 0
    latest_complete: str | None = None
    config: list[dict] = field(default_factory=list)


def fetch_day(
    day: dt.date,
    datapool: Path,
    *,
    today: dt.date,
    result: Result,
    get: collections.abc.Callable[[str], bytes] | None = None,
    base: str = MIRROR,
    late_days: int = LATE_DAYS,
    dry_run: bool = False,
) -> bool:
    """Fetch what this day lacks. True if the day is complete afterwards."""
    get = get or http_get
    year, doy = day_name(day)
    complete = True
    for label, folder, pattern in PRODUCTS:
        name = pattern.format(y=year, d=doy)
        dest = datapool / folder / name
        if dest.is_file():
            continue
        if dry_run:
            print(f"would fetch {name}")
            complete = False
            continue
        try:
            data = get(f"{base}/CODE/{year}/{name}")
            # A partial body with a success status would otherwise fail only inside a BPE.
            if not gzip.decompress(data):
                raise ValueError("empty after decompressing")
        except NotPublished:
            complete = False
            if (today - day).days > late_days:
                result.late.append(f"{year} DOY {doy} {label}")
            else:
                result.waiting += 1
            continue
        except (OSError, EOFError, zlib.error, ValueError) as exc:
            complete = False
            result.errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:160]}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        part.write_bytes(data)
        os.replace(part, dest)
        result.fetched.append(name)
    return complete


def fetch_range(
    start: dt.date,
    today: dt.date,
    datapool: Path,
    result: Result,
    **kw: object,
) -> None:
    day = start
    while day <= today:
        if fetch_day(day, datapool, today=today, result=result, **kw):  # type: ignore[arg-type]
            year, doy = day_name(day)
            result.latest_complete = f"{year} DOY {doy}"
        day += dt.timedelta(days=1)


def compare_watched(
    config_dir: Path,
    ref_dir: Path,
    year: int,
    *,
    head: collections.abc.Callable[[str], tuple[int, float | None]] | None = None,
    base: str = MIRROR,
) -> tuple[list[dict], list[str]]:
    """How each watched file compares with AIUB's. Nothing is written.

    A different size is what counts as out of date. The mirror's dates alone can't: it
    re-uploads whole folders, so an unchanged file can carry a newer date.
    """
    head = head or http_head
    out: list[dict] = []
    errors: list[str] = []
    for mirror_dir, where, pattern in WATCHED:
        name = pattern.format(y=year)
        local = (config_dir if where == "CONFIG" else ref_dir) / name
        try:
            size, when = head(f"{base}/BSWUSER54/{mirror_dir}/{name}")
        except NotPublished:
            continue
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:160]}")
            continue
        entry: dict = {"file": name, "aiub_size": size, "aiub_date": _date(when)}
        if local.is_file():
            st = local.stat()
            entry |= {"local_size": st.st_size, "local_date": _date(st.st_mtime)}
            entry["out_of_date"] = st.st_size != size
        else:
            entry |= {"local_size": None, "local_date": None, "out_of_date": True}
        out.append(entry)
    return out, errors


def _date(stamp: float | None) -> str | None:
    if stamp is None:
        return None
    return dt.datetime.fromtimestamp(stamp, dt.UTC).date().isoformat()


def status_path(state: Path | None = None) -> Path:
    return (state or default_state_dir()) / "products" / "status.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", type=dt.date.fromisoformat, help="fill back to this date, YYYY-MM-DD")
    ap.add_argument("--lookback", type=int, default=LOOKBACK_DAYS, help="days back to check nightly")
    ap.add_argument("--late-days", type=int, default=LATE_DAYS)
    ap.add_argument("--state", type=Path, default=None, help="the worker's state directory")
    ap.add_argument("--dry-run", action="store_true", help="print what it would fetch; write nothing")
    args = ap.parse_args(argv)

    home = Path.home()
    datapool = Path(os.environ.get("D") or home / "GPSDATA/DATAPOOL")
    config_dir = Path(os.environ.get("CONFIG") or home / "BERN54/GLOBAL/CONFIG")
    if not datapool.is_dir():
        print(f"bernese-update-products: {datapool} isn't a directory", file=sys.stderr)
        return 2

    now = now_utc()
    today = now.date()
    start = args.since or today - dt.timedelta(days=args.lookback)
    result = Result()
    fetch_range(start, today, datapool, result, late_days=args.late_days, dry_run=args.dry_run)
    result.config, config_errors = compare_watched(config_dir, datapool / "REF54", today.year)
    result.errors += config_errors

    for name in result.fetched:
        print(f"fetched {name}")
    for line in result.errors:
        print(f"bernese-update-products: {line}", file=sys.stderr)
    stale = [e for e in result.config if e["out_of_date"]]
    print(
        f"{len(result.fetched)} fetched, {result.waiting} not published yet, {len(result.late)} late, "
        f"{len(result.errors)} errors; latest complete day {result.latest_complete}; "
        f"{len(stale)} of {len(result.config)} watched files differ from AIUB's"
    )
    for entry in stale:
        print(
            f"  differs: {entry['file']}: here {entry['local_size']} bytes, {entry['local_date']}; "
            f"AIUB {entry['aiub_size']} bytes, {entry['aiub_date']}"
        )
    if args.dry_run:
        return 0
    path = status_path(args.state)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        path,
        {
            "last_pass": now.isoformat(),
            "fetched": len(result.fetched),
            "waiting": result.waiting,
            "late": result.late,
            "errors": result.errors,
            "latest_complete": result.latest_complete,
            "config": result.config,
        },
        tmp_dir=path.parent,
    )
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
