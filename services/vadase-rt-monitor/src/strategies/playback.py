from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime, timedelta, date

class PlaybackStrategy(ABC):
    """
    Strategy for controlling the rate of line emission.
    """
    @abstractmethod
    async def wait(self, line: str) -> None:
        """
        Determines and executes the wait time before processing the next line.
        """
        pass

class FastImportStrategy(PlaybackStrategy):
    """
    No waiting; process as fast as possible.
    """
    async def wait(self, line: str) -> None:
        return

class RealTimeStrategy(PlaybackStrategy):
    """
    Simulates real-time delays based on difference between timestamps
    in consecutive NMEA lines.
    """
    def __init__(self, base_date: Optional[date] = None):
        self.current_date = base_date or datetime.now().date()
        self.last_timestamp: Optional[datetime] = None

    async def wait(self, line: str) -> None:
        try:
            current_dt = self._extract_datetime(line)
            
            if self.last_timestamp is not None:
                delta = (current_dt - self.last_timestamp).total_seconds()
                # Sanity check: valid positive delay, not too huge
                if 0 < delta < 60:
                    import asyncio
                    await asyncio.sleep(delta)
            
            self.last_timestamp = current_dt
        except ValueError:
            pass

    def _extract_datetime(self, line: str) -> datetime:
        """
        Extracts HHMMSS.ss and handles day rollover.
        Copied/Refactored from original FileSource logic.
        """
        parts = line.split(',')
        if len(parts) < 2 or not parts[1]:
            raise ValueError("No timestamp")

        raw_time = parts[1]
        try:
            time_obj = datetime.strptime(raw_time.split('.')[0], "%H%M%S").time()
            dt = datetime.combine(self.current_date, time_obj)
            
            # Handle rollover
            if self.last_timestamp:
                 # If time jumped back >12h, assume next day
                if (self.last_timestamp - dt).seconds > 43200:
                    self.current_date += timedelta(days=1)
                    dt = datetime.combine(self.current_date, time_obj)
            
            return dt
        except ValueError:
             raise ValueError("Invalid format")
