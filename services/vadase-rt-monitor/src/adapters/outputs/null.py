from datetime import datetime
from typing import Any, Dict


class NullOutputPort:
    """
    No-op OutputPort for tests and dry-run mode.

    All writes are silently discarded.  connect() and close() are no-ops.
    Satisfies the OutputPort Protocol without a real database.
    """

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def write_velocity(self, station_id: str, data: Dict[str, Any]) -> None:
        pass

    async def write_displacement(self, station_id: str, data: Dict[str, Any]) -> None:
        pass

    async def write_event_detection(
        self,
        station: str,
        detection_time: datetime,
        peak_velocity: float,
        peak_displacement: float,
        duration: float,
    ) -> None:
        pass
