import gzip
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import click
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# GPS epoch for week/DOW calculation
_GPS_EPOCH = datetime(1980, 1, 6)

# GPS week at which IGS20 long filenames replaced short names (27 Nov 2022)
_IGS20_TRANSITION_WEEK = 2238

# Ordered by preference: IGN and BKG are anonymous; CDDIS requires Earthdata Login
_DEFAULT_MIRRORS = [
    "https://igs.ign.fr/pub/igs/products/",
    "https://igs.bkg.bund.de/root_ftp/IGS/products/",
    "https://cddis.nasa.gov/archive/gnss/products/",
]

# Maps (analysis_centre, content) → (sampling_interval, format_extension)
# IGS combined uses 15-min orbit sampling; CODE uses 5-min
_PRODUCT_TABLE: dict[tuple[str, str], tuple[str, str]] = {
    ("IGS", "ORB"): ("15M", "SP3"),
    ("IGS", "CLK"): ("05M", "CLK"),
    ("COD", "ORB"): ("05M", "SP3"),
    ("COD", "CLK"): ("30S", "CLK"),
}


def _gps_week(date: datetime) -> int:
    return (date - _GPS_EPOCH).days // 7


def _day_of_year(date: datetime) -> int:
    return date.timetuple().tm_yday


def _build_long_filename(ac: str, date: datetime, content: str) -> str:
    """Return IGS20 long filename for the given analysis centre, date, and content type."""
    smp, fmt = _PRODUCT_TABLE[(ac, content)]
    yyyy = date.year
    ddd = f"{_day_of_year(date):03d}"
    return f"{ac}0OPSFIN_{yyyy}{ddd}0000_01D_{smp}_{content}.{fmt}.gz"


def _build_legacy_filename(ac: str, gps_week: int, gps_dow: int, content: str) -> str:
    """Return pre-IGS20 short filename (pre-GPS week 2238 dates only)."""
    ac_lower = ac.lower()
    if content == "ORB":
        return f"{ac_lower}{gps_week}{gps_dow}.sp3.Z"
    return f"{ac_lower}{gps_week}{gps_dow}.clk.Z"


class ProductDownloader:
    def __init__(self, base_dir: str = "data/igs", mirrors: Optional[list[str]] = None):
        self.base_dir = base_dir
        self.mirrors = mirrors or _DEFAULT_MIRRORS
        self.session = requests.Session()

    def download_product(
        self,
        date: datetime,
        ac: str = "COD",
        content: str = "ORB",
        force: bool = False,
    ) -> Optional[str]:
        """Download an IGS/CODE orbit or clock product for *date*.

        Returns the local path to the decompressed file, or None on failure.
        ac: analysis centre — "IGS" or "COD"
        content: "ORB" (orbits) or "CLK" (clocks)
        """
        week = _gps_week(date)
        gps_dow = (date - _GPS_EPOCH).days % 7

        use_long = week >= _IGS20_TRANSITION_WEEK
        if use_long:
            filename_gz = _build_long_filename(ac, date, content)
        else:
            filename_gz = _build_legacy_filename(ac, week, gps_dow, content)

        # Local storage path: base_dir/YYYY/DDD/<decompressed_filename>
        ddd = f"{_day_of_year(date):03d}"
        target_dir = os.path.join(self.base_dir, str(date.year), ddd)
        os.makedirs(target_dir, exist_ok=True)

        # Strip .gz / .Z for the stored file
        local_name = filename_gz.removesuffix(".gz").removesuffix(".Z")
        local_path = os.path.join(target_dir, local_name)

        if os.path.exists(local_path) and not force:
            logger.info("already_exists path=%s", local_path)
            return local_path

        for mirror in self.mirrors:
            url = f"{mirror}{week}/{filename_gz}"
            logger.info("attempting url=%s", url)
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code == 200:
                    raw = response.content
                    # Decompress .gz (IGS20) or .Z (legacy, best-effort)
                    if filename_gz.endswith(".gz"):
                        data = gzip.decompress(raw)
                    else:
                        # Legacy .Z — requires unix compress; fall back to raw storage
                        logger.warning("legacy_.Z_decompression_not_supported storing_raw")
                        data = raw
                    with open(local_path, "wb") as f:
                        f.write(data)
                    logger.info("downloaded path=%s", local_path)
                    return local_path
                logger.warning("http_error url=%s status=%s", url, response.status_code)
            except Exception as e:
                logger.error("download_error url=%s error=%s", url, e)

        logger.error("all_mirrors_failed filename=%s", filename_gz)
        return None


@click.command()
@click.option("--date", "date_str", type=click.DateTime(formats=["%Y-%m-%d"]), help="Date (YYYY-MM-DD)")
@click.option("--days-ago", type=int, help="Number of days ago to download")
@click.option("--ac", default="COD", show_default=True, help="Analysis centre: IGS or COD")
@click.option("--content", default="ORB", show_default=True, help="Content type: ORB or CLK")
@click.option("--output-dir", default="data/igs", show_default=True, help="Base directory for downloads")
@click.option("--force", is_flag=True, help="Force re-download even if file exists")
def main(
    date_str: Optional[datetime],
    days_ago: Optional[int],
    ac: str,
    content: str,
    output_dir: str,
    force: bool,
) -> None:
    """Download IGS/CODE GNSS orbit and clock products."""
    if days_ago is not None:
        date_str = datetime.now() - timedelta(days=days_ago)

    if date_str is None:
        click.echo("Error: provide --date or --days-ago", err=True)
        return

    downloader = ProductDownloader(base_dir=output_dir)
    result = downloader.download_product(date_str, ac=ac.upper(), content=content.upper(), force=force)
    if result is None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
