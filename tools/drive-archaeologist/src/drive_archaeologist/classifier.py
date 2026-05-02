"""
File classification based on extension profiles.
"""

from pathlib import Path
from typing import Dict, List, Optional

from .profiles import CLASSIFICATION_PROFILES


class Classifier:
    """
    Classifies files based on a predefined set of extension profiles.
    """

    def __init__(self):
        """
        Initializes the classifier by building a reverse mapping from extension to category.
        """
        self._extension_map: Dict[str, str] = self._build_extension_map()

    def _build_extension_map(self) -> Dict[str, str]:
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

    def classify(self, filepath: Path) -> Optional[str]:
        """
        Classify a file based on its extension.

        Args:
            filepath: The path to the file.

        Returns:
            The classification category as a string, or None if no match is found.
        """
        extension = filepath.suffix.lower()
        return self._extension_map.get(extension)
