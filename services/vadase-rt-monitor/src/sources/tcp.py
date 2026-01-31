import asyncio
import structlog
from typing import AsyncIterator

logger = structlog.get_logger()

class TcpSource:
    """
    Ingests NMEA data from a TCP stream (CORS station).
    Handles persistence connection and automatic reconnection.
    """
    def __init__(self, host: str, port: int, station_id: str):
        self.host = host
        self.port = port
        self.station_id = station_id
        self.reader = None
        self.writer = None
        self.logger = logger.bind(station=station_id, source="tcp")

    async def connect(self) -> None:
        """
        No-op for TCP wrapper as connection is handled in iterator loop
        or could verify connectivity here.
        """
        pass

    async def close(self) -> None:
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None

    async def __aiter__(self) -> AsyncIterator[str]:
        """
        Yields NMEA lines indefinitely, automatically reconnecting on failure.
        """
        while True:
            try:
                self.logger.info("connecting", host=self.host, port=self.port)
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                self.logger.info("connected")

                buffer = ""
                while True:
                    # Read with timeout to detect stale connections
                    try:
                        data = await asyncio.wait_for(self.reader.read(4096), timeout=30.0)
                    except asyncio.TimeoutError:
                        self.logger.warning("timeout_no_data", timeout_sec=30)
                        break

                    if not data:
                        self.logger.warning("connection_closed_by_receiver")
                        break

                    # Accumulate data in buffer
                    buffer += data.decode('ascii', errors='ignore')

                    # Process complete sentences
                    while '\n' in buffer:
                        sentence, buffer = buffer.split('\n', 1)
                        sentence = sentence.strip()
                        if sentence:
                            yield sentence

                # If inner loop breaks, clean up before reconnecting
                await self.close()

            except Exception as e:
                self.logger.error("connection_error", error=str(e))
                await self.close()

            # Wait before reconnecting
            self.logger.info("reconnecting_in", seconds=5)
            await asyncio.sleep(5)
