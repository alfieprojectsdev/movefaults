import asyncio
import aiofiles
from datetime import datetime, timedelta, date
from typing import AsyncIterator, Optional
from pathlib import Path

class FileSource:
    """
    Ingests NMEA data from a local file for offline analysis or testing.
    
    Modes:
    - 'import': Yields lines as fast as possible (for bulk DB loading).
    - 'replay': Yields lines with delays matching the original event timing.
    """
    def __init__(
        self, 
        file_path: Path | str, 
        mode: str = "import", 
        base_date: Optional[date] = None
    ):
        self.file_path = Path(file_path)
        self.mode = mode
        # Default to today if no date provided, useful for testing recent logs
        self.current_date = base_date or datetime.now().date()
        self.last_timestamp: Optional[datetime] = None
        self._file_handle = None

    async def connect(self) -> None:
        if not self.file_path.exists():
            raise FileNotFoundError(f"NMEA source file not found: {self.file_path}")
        # We don't keep the file open here; we open it in the iterator for safety
        pass

    async def close(self) -> None:
        pass

    async def __aiter__(self) -> AsyncIterator[str]:
        async with aiofiles.open(self.file_path, mode='r') as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue

                # 1. In 'replay' mode, we must simulate the time gap
                if self.mode == "replay":
                    await self._simulate_delay(line)

                # 2. Yield the line to the parser
                yield line

    async def _simulate_delay(self, nmea_line: str):
        """
        Parses the NMEA timestamp and sleeps for the delta between
        this line and the previous line.
        """
        try:
            current_dt = self._extract_datetime(nmea_line)
            
            if self.last_timestamp is not None:
                # Calculate time difference
                delta = (current_dt - self.last_timestamp).total_seconds()
                
                # Sanity check: If delta is huge or negative (out of order), ignore sleep
                if 0 < delta < 60:  
                    await asyncio.sleep(delta)
            
            self.last_timestamp = current_dt

        except ValueError:
            # If line is malformed or not a time-bearing sentence, 
            # just yield it immediately (skip sleep)
            pass

    def _extract_datetime(self, line: str) -> datetime:
        """
        Extracts HHMMSS.ss from NMEA (e.g., $GPGGA,123456.78,...)
        and combines it with self.current_date.
        Handles day rollover (if time jumps backward).
        """
        parts = line.split(',')
        # GPGGA/GPRMC/VADASE usually have time at index 1
        # Check basic validity
        if len(parts) < 2 or not parts[1]:
            raise ValueError("No timestamp found")

        # Parse HHMMSS.ss
        raw_time = parts[1]
        try:
            # Robust parsing for variable decimals
            time_obj = datetime.strptime(raw_time.split('.')[0], "%H%M%S").time()
            
            # Combine with current base date
            dt = datetime.combine(self.current_date, time_obj)
            
            # Handle Midnight Rollover:
            # If the new time is significantly earlier than the last time seen,
            # we assume we crossed into the next day.
            if self.last_timestamp and dt.time() < self.last_timestamp.time():
                 # Basic heuristic: if time jumped back more than 12 hours, it's a new day
                 # (Avoids triggering on small out-of-order packets)
                if (self.last_timestamp - dt).seconds > 43200:
                    self.current_date += timedelta(days=1)
                    dt = datetime.combine(self.current_date, time_obj)

            return dt
        except ValueError:
             raise ValueError("Invalid timestamp format")
