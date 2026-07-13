import asyncio
import base64
import random
import structlog
from typing import Optional
from src.ports.inputs import InputPort

logger = structlog.get_logger()


class FatalConfigError(ConnectionError):
    """A handshake failure that retrying cannot fix (bad credentials, wrong
    mountpoint). Retrying these hammers the caster with bad-auth requests and
    risks locking the shared account — the station must stop instead."""


class TCPAdapter(InputPort):
    """
    Input Adapter for TCP Streams (NTRIP Client).
    """

    HANDSHAKE_TIMEOUT = 10.0  # seconds; the 10 s data watchdog doesn't cover the handshake

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
                    # readline() inside the handshake has no watchdog of its own;
                    # a caster that accepts TCP but never responds would hang forever.
                    await asyncio.wait_for(
                        self._perform_handshake(), timeout=self.HANDSHAKE_TIMEOUT
                    )

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

            except FatalConfigError as e:
                self.logger.error(
                    "fatal_config_error", error=str(e),
                    hint="fix station credentials/mountpoint and restart; not retrying",
                )
                await self.cleanup()
                return
            except Exception as e:
                self.logger.error("connection_error", error=str(e))
                await self.cleanup()

            if not stop_event.is_set():
                # Full jitter across [base, backoff]: after a shared caster outage,
                # 35 stations must not reconnect in lockstep at each backoff step.
                delay = random.uniform(_BACKOFF_BASE, backoff)
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
            raise FatalConfigError(
                f"NTRIP mountpoint '{self.mountpoint}' is not an active stream "
                f"(caster returned SOURCETABLE); verify mountpoint name"
            )
        if "200 OK" in response_str:
            # NTRIP 1.0 casters reply "ICY 200 OK" and stream data immediately —
            # no headers, no blank line; draining would eat the first NMEA
            # sentences of every (re)connect. Only HTTP-style responses
            # (NTRIP 2.0) carry a header block to drain.
            if response_str.startswith("HTTP/"):
                await self._drain_http_headers()
            self.logger.info("handshake_success", response=response_str)
            return
        if "401" in response_str:
            raise FatalConfigError("NTRIP unauthorized: check credentials")
        if "404" in response_str:
            raise FatalConfigError(f"NTRIP mountpoint not found: {self.mountpoint}")
        raise ConnectionError(f"NTRIP handshake failed: {response_str}")

    async def _drain_http_headers(self) -> None:
        """Consume remaining HTTP response headers until the blank separator line."""
        for _ in range(32):  # guard against malformed/infinite responses
            line = await self.reader.readline()
            if not line.strip():
                break

