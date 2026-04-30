import asyncio
import base64
import random
import structlog
from typing import Optional
from src.ports.inputs import InputPort

logger = structlog.get_logger()

class TCPAdapter(InputPort):
    """
    Input Adapter for TCP Streams (NTRIP Client).
    """
    def __init__(
        self, 
        host: str, 
        port: int, 
        station_id: str,
        mountpoint: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.station_id = station_id
        self.mountpoint = mountpoint
        self.user = user
        self.password = password
        
        self.reader = None
        self.writer = None
        self.logger = logger.bind(station=station_id, source="ntrip_adapter")

    async def start(self, queue: asyncio.Queue, stop_event: asyncio.Event) -> None:
        MAX_BUFFER_SIZE = 64 * 1024  # 64KB
        _BACKOFF_BASE = 5.0
        _BACKOFF_MAX = 60.0
        backoff = _BACKOFF_BASE

        while not stop_event.is_set():
            try:
                self.logger.info("connecting", host=self.host, port=self.port, mountpoint=self.mountpoint)
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

                if self.mountpoint:
                    await self._perform_handshake()

                self.logger.info("connected")
                backoff = _BACKOFF_BASE  # reset on successful connection

                buffer = ""

                while not stop_event.is_set():
                    try:
                        # Watchdog: 10s timeout
                        data = await asyncio.wait_for(self.reader.read(4096), timeout=10.0)
                    except asyncio.TimeoutError:
                        self.logger.warning("watchdog_timeout", seconds=10)
                        break

                    if not data:
                        self.logger.warning("connection_closed_by_remote")
                        break

                    buffer += data.decode('ascii', errors='ignore')

                    if len(buffer) > MAX_BUFFER_SIZE:
                        self.logger.warning("buffer_overflow", size=len(buffer), limit=MAX_BUFFER_SIZE)
                        break

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
                jitter = random.uniform(0.0, 1.0)
                delay = backoff + jitter
                self.logger.info("reconnecting_in", seconds=round(delay, 1))
                await asyncio.sleep(delay)
                backoff = min(backoff * 2, _BACKOFF_MAX)

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

    async def _perform_handshake(self):
        """Sends NTRIP GET request, validates ICY 200 OK, drains remaining headers."""
        headers = [
            f"GET /{self.mountpoint} HTTP/1.0",
            "User-Agent: NTRIP Python/1.0",
            "Accept: */*",
            "Connection: close",
        ]
        if self.user and self.password:
            auth_str = f"{self.user}:{self.password}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            headers.append(f"Authorization: Basic {b64_auth}")

        self.writer.write(("\r\n".join(headers) + "\r\n\r\n").encode())
        await self.writer.drain()

        response_line = await self.reader.readline()
        response_str = response_line.decode().strip()

        if "SOURCETABLE" in response_str:
            raise ConnectionError(
                f"NTRIP mountpoint '{self.mountpoint}' is not an active stream "
                f"(caster returned SOURCETABLE); verify mountpoint name"
            )
        if "200 OK" in response_str:
            await self._drain_http_headers()
            self.logger.info("handshake_success", response=response_str)
            return
        if "401" in response_str:
            raise ConnectionError("NTRIP unauthorized: check credentials")
        if "404" in response_str:
            raise ConnectionError(f"NTRIP mountpoint not found: {self.mountpoint}")
        raise ConnectionError(f"NTRIP handshake failed: {response_str}")

    async def _drain_http_headers(self) -> None:
        """Consume remaining HTTP response headers until the blank separator line."""
        for _ in range(32):  # guard against malformed/infinite responses
            line = await self.reader.readline()
            if not line.strip():
                break

