import requests
import os
import click
from datetime import datetime, timedelta
import logging
from typing import List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProductDownloader:
    def __init__(self, base_dir: str = "data/igs", mirrors: Optional[List[str]] = None):
        self.base_dir = base_dir
        self.mirrors = mirrors or [
            "https://cddis.nasa.gov/archive/gnss/products/",
            "https://igs.ign.fr/pub/igs/products/",
        ]
        self.session = requests.Session()

    def _get_gps_week_dow(self, date: datetime):
        """Calculates GPS week and day of week."""
        gps_epoch = datetime(1980, 1, 6)
        td = date - gps_epoch
        gps_week = td.days // 7
        gps_dow = td.days % 7
        return gps_week, gps_dow

    def download_product(self, date: datetime, product_type: str = "final", force: bool = False):
        """Downloads IGS products for a specific date."""
        gps_week, gps_dow = self._get_gps_week_dow(date)
        
        # Example for CODE final products: codwwwwd.sp3.Z
        # This is a simplified example, real IGS naming is complex
        filename = f"cod{gps_week}{gps_dow}.sp3.Z"
        
        target_dir = os.path.join(self.base_dir, str(date.year), f"{date.timetuple().tm_yday:03d}")
        os.makedirs(target_dir, exist_ok=True)
        local_path = os.path.join(target_dir, filename)

        if os.path.exists(local_path) and not force:
            logger.info(f"File already exists, skipping: {local_path}")
            return local_path

        for mirror in self.mirrors:
            url = f"{mirror}{gps_week}/{filename}"
            logger.info(f"Attempting download from: {url}")
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"Successfully downloaded: {local_path}")
                    return local_path
                else:
                    logger.warning(f"Failed to download from {url}: {response.status_code}")
            except Exception as e:
                logger.error(f"Error downloading from {url}: {e}")

        logger.error(f"Failed to download {filename} from all mirrors.")
        return None

@click.command()
@click.option("--date", type=click.DateTime(formats=["%Y-%m-%d"]), help="Date to download for (YYYY-MM-DD)")
@click.option("--days-ago", type=int, help="Number of days ago to download")
@click.option("--output-dir", default="data/igs", help="Base directory for downloads")
@click.option("--force", is_flag=True, help="Force re-download")
def main(date: Optional[datetime], days_ago: Optional[int], output_dir: str, force: bool):
    """IGS Product Downloader CLI"""
    if days_ago is not None:
        date = datetime.now() - timedelta(days=days_ago)
    
    if date is None:
        click.echo("Error: Must provide either --date or --days-ago", err=True)
        return

    downloader = ProductDownloader(base_dir=output_dir)
    downloader.download_product(date, force=force)

if __name__ == "__main__":
    main()
