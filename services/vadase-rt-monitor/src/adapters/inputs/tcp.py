import asyncio
import structlog
from src.ports.inputs import InputPort

logger = structlog.get_logger()

class TCPAdapter(InputPort):
    """
    Input Adapter for TCP Streams.
    """
    def __init__(self, host: str, port: int, station_id: str):
        self.host = host
        self.port = port
        self.station_id = station_id
        self.reader = None
        self.writer = None
        self.logger = logger.bind(station=station_id, source="tcp_adapter")

    async def start(self, queue: asyncio.Queue, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                self.logger.info("connecting", host=self.host, port=self.port)
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                self.logger.info("connected")

                buffer = ""
                while not stop_event.is_set():
                    try:
                        data = await asyncio.wait_for(self.reader.read(4096), timeout=30.0)
                    except asyncio.TimeoutError:
                        self.logger.warning("timeout_no_data")
                        break
                    
                    if not data:
                        break

                    buffer += data.decode('ascii', errors='ignore')
                    while '\n' in buffer:
                        sentence, buffer = buffer.split('\n', 1)
                        sentence = sentence.strip()
                        if sentence:
                            await queue.put(sentence)

                await self.cleanup()

            except Exception as e:
                self.logger.error("connection_error", error=str(e))
                await self.cleanup()

            if not stop_event.is_set():
                await asyncio.sleep(5)

    async def stop(self) -> None:
        await self.cleanup()

    async def cleanup(self):
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
            self.writer = None
