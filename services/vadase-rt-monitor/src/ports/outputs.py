from typing import Protocol, Any, Dict
from datetime import datetime

class OutputPort(Protocol):
    """
    Port (Interface) for data egress (Database, Plotter).
    """
    async def connect(self) -> None:
        ...

    async def close(self) -> None:
        ...

    async def write_velocity(self, station_id: str, data: Dict[str, Any]) -> None:
        ...

    async def write_displacement(self, station_id: str, data: Dict[str, Any]) -> None:
        ...

    async def write_event_detection(
        self, 
        station: str, 
        detection_time: datetime, 
        peak_velocity: float, 
        peak_displacement: float, 
        duration: float
    ) -> None:
        ...
