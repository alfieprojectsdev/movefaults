import os
import re

from . import Strategy

# Trimble proprietary raw extensions (case-insensitive on scan)
_TRIMBLE_EXTS = frozenset([".t01", ".t02", ".t04", ".tgd"])


class TrimbleStrategy(Strategy):
    """Matches Trimble proprietary raw GNSS files (NetR9, 5700, etc.).

    Tagged with requires_conversion=True because these cannot be ingested
    directly; teqc or runpkr00 must convert them to RINEX first.
    """

    def match(self, path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in _TRIMBLE_EXTS

    def extract(self, path: str) -> dict | None:
        filename = os.path.basename(path)
        ext = os.path.splitext(filename)[1].lower()
        return {
            "type": "gnss_trimble_raw",
            "filename": filename,
            "extension": ext,
            "requires_conversion": True,
        }


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
