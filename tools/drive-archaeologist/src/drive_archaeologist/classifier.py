"""
File classification based on extension profiles.
"""

import re
from pathlib import Path

from .profiles import CLASSIFICATION_PROFILES

# RINEX 2 short filename: ssssdddh.yyt (site, DOY, session, 2-digit year, type).
# The profile extension list only enumerates years .15–.22; real archives span
# far more (e.g. .05o, .23o) and include Hatanaka (.yyd) and met (.yym) files.
# o=obs n=nav g=GLONASS-nav d=Hatanaka m=met
_RINEX_SHORT_RE = re.compile(r"^[a-z0-9]{4}\d{3}[a-x0-9]\.\d{2}[ondgm]$", re.IGNORECASE)


class Classifier:
    """
    Classifies files based on a predefined set of extension profiles.
    """

    def __init__(self):
        """
        Initializes the classifier by building a reverse mapping from extension to category.
        """
        self._extension_map: dict[str, str] = self._build_extension_map()

    def _build_extension_map(self) -> dict[str, str]:
        """
        Creates a direct mapping from a file extension to its classification category.

        This is more efficient for lookups than iterating through the profiles list every time.
        Example: {'.pdf': 'Document', '.jpg': 'Image'}
        """
        ext_map = {}
        for category, extensions in CLASSIFICATION_PROFILES.items():
            for ext in extensions:
                ext_map[ext] = category
        return ext_map

    def classify(self, filepath: Path) -> str | None:
        """
        Classify a file based on its extension, with a RINEX short-name
        regex fallback for year-extensions absent from the profile list.

        Args:
            filepath: The path to the file.

        Returns:
            The classification category as a string, or None if no match is found.
        """
        extension = filepath.suffix.lower()
        category = self._extension_map.get(extension)
        if category is not None:
            return category
        if _RINEX_SHORT_RE.match(filepath.name):
            return "GNSS Data"
        return None

    def classify_by_ext(self, ext: str) -> str | None:
        return self._extension_map.get(ext.lower())
