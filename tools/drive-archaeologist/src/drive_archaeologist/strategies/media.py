import os
import re

from . import Strategy


class MediaStrategy(Strategy):
    # Matches Show.Name.S01E02.ext or Show Name S01E02.ext
    # Flexible on separators, looks for SXXEXX pattern.
    PATTERN = re.compile(r'(?P<series>.+?)[\._\s][Ss](?P<season>\d{1,2})[Ee](?P<episode>\d{1,2})')
    EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov'}

    def match(self, path: str) -> bool:
        _, ext = os.path.splitext(path)
        return ext.lower() in self.EXTENSIONS

    def extract(self, path: str) -> dict | None:
        filename = os.path.basename(path)
        match = self.PATTERN.search(filename)
        if match:
            data = match.groupdict()
            return {
                "type": "tv_show",
                "series": data['series'].replace('.', ' ').strip(),
                "season": int(data['season']),
                "episode": int(data['episode'])
            }
        
        # Fallback for just movie files or non-episodic?
        # For now, per requirements, we just identify what we can.
        return {
            "type": "video_unknown",
            "filename": filename
        }
