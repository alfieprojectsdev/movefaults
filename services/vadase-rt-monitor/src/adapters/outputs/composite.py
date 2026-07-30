from datetime import datetime
from typing import Any

from src.ports.outputs import OutputPort


class CompositeOutputPort:
    """
    Fan-out to multiple OutputPort instances (e.g. DB + live plotter).

    Lives at the port layer so every entry point composes outputs the same
    way — previously each script carried its own copy of this class, and a
    new OutputPort method silently no-op'd in whichever copy wasn't updated.
    """

    def __init__(self, writers: list[OutputPort]):
        self.writers = writers

    async def connect(self) -> None:
        for w in self.writers:
            await w.connect()

    async def close(self) -> None:
        for w in self.writers:
            await w.close()

    async def write_velocity(self, station_id: str, data: dict[str, Any]) -> None:
        for w in self.writers:
            await w.write_velocity(station_id, data)

    async def write_displacement(self, station_id: str, data: dict[str, Any]) -> None:
        for w in self.writers:
            await w.write_displacement(station_id, data)

    async def write_event_detection(
        self,
        station: str,
        detection_time: datetime,
        peak_velocity: float,
        peak_displacement: float,
        duration: float,
    ) -> None:
        for w in self.writers:
            await w.write_event_detection(
                station, detection_time, peak_velocity, peak_displacement, duration
            )
