import os
import re

from . import Strategy


class GNSSStrategy(Strategy):
    # Matches standard RINEX short filenames: ssssdddh.yyt
    # e.g., site0010.23o
    # station (4), doy (3), session (1) . year (2) type (1)
    # Also accepting *.*o as per user request broadly, but we try to parse the bits.
    PATTERN = re.compile(r'^(?P<station>[a-zA-Z0-9]{4})(?P<doy>\d{3})(?P<session>[a-zA-Z0-9])\.(?P<year>\d{2})(?P<type>[oOnNgG])$')

    def match(self, path: str) -> bool:
        filename = os.path.basename(path)
        return self.PATTERN.match(filename) is not None

    def extract(self, path: str) -> dict | None:
        filename = os.path.basename(path)
        match = self.PATTERN.match(filename)
        if match:
            data = match.groupdict()
            return {
                "type": "gnss_rinex",
                "station": data['station'],
                "doy": int(data['doy']),
                "session": data['session'],
                "year": int(data['year']),  # 2-digit year
                "file_type": data['type']
            }
        
        if re.search(r'\.\d{2}[oO]$', filename):
            return {
                "type": "gnss_rinex_possible",
                "filename": filename
            }
        return None
