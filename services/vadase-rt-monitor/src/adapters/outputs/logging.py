from datetime import datetime
from typing import Any

import structlog


class LoggingOutputPort:
    """
    Dry-run OutputPort that logs every write instead of discarding it.

    Used by run_ingestor --dry-run so an operator verifying a new station's
    NTRIP config can SEE data flowing (or not) before going live — a silent
    NullOutputPort makes a misconfigured stream indistinguishable from a
    healthy one.
    """

    def __init__(self) -> None:
        self.log = structlog.get_logger().bind(sink="dry-run")

    async def connect(self) -> None:
        self.log.info("dry_run_active", note="all writes logged, nothing persisted")

    async def close(self) -> None:
        pass

    async def write_velocity(self, station_id: str, data: dict[str, Any]) -> None:
        self.log.info(
            "VEL", station=station_id, t=str(data.get("timestamp")),
            vE=data.get("vE"), vN=data.get("vN"), vU=data.get("vU"),
        )

    async def write_displacement(self, station_id: str, data: dict[str, Any]) -> None:
        self.log.info(
            "DSP", station=station_id, t=str(data.get("timestamp")),
            dE=data.get("dE"), dN=data.get("dN"), dU=data.get("dU"),
            source=data.get("displacement_source"),
        )

    async def write_event_detection(
        self,
        station: str,
        detection_time: datetime,
        peak_velocity: float,
        peak_displacement: float,
        duration: float,
    ) -> None:
        self.log.warning(
            "EVENT DETECTED", station=station, t=str(detection_time),
            peak_velocity=peak_velocity, peak_displacement=peak_displacement,
            duration=duration,
        )
