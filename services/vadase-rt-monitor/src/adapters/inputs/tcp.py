import asyncio
import base64
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
        while not stop_event.is_set():
            try:
                self.logger.info("connecting", host=self.host, port=self.port, mountpoint=self.mountpoint)
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                
                # NTRIP Handshake if mountpoint is provided
                if self.mountpoint:
                    await self._perform_handshake()
                
                self.logger.info("connected")

                buffer = ""
                last_data_time = asyncio.get_event_loop().time()
                
                while not stop_event.is_set():
                    try:
                        # Watchdog: 10s timeout
                        data = await asyncio.wait_for(self.reader.read(4096), timeout=10.0)
                        last_data_time = asyncio.get_event_loop().time()
                    except asyncio.TimeoutError:
                        self.logger.warning("watchdog_timeout", seconds=10)
                        break # Break inner loop to trigger reconnect
                    
                    if not data:
                        self.logger.warning("connection_closed_by_remote")
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

            # Retry delay
            if not stop_event.is_set():
                self.logger.info("reconnecting_in", seconds=5)
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

    async def _perform_handshake(self):
        """
        Sends NTRIP GET request and validates response.
        """
        # 1. Construct Headers
        headers = [
            f"GET /{self.mountpoint} HTTP/1.0",
            "User-Agent: NTRIP Python/1.0",
            "Accept: */*",
            "Connection: close"
        ]
        
        if self.user and self.password:
            auth_str = f"{self.user}:{self.password}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            headers.append(f"Authorization: Basic {b64_auth}")
        
        request = "\r\n".join(headers) + "\r\n\r\n"
        
        # 2. Send Request
        self.writer.write(request.encode())
        await self.writer.drain()
        
        # 3. Read Response Headers
        response_line = await self.reader.readline()
        response_str = response_line.decode().strip()
        
        if "200 OK" in response_str:
            self.logger.info("handshake_success", response=response_str)
            return
            
        elif "401" in response_str:
            raise ConnectionError(f"NTRIP Unauthorized: {response_str}")
        elif "404" in response_str:
             raise ConnectionError(f"NTRIP Mountpoint Not Found: {response_str}")
        else:
             raise ConnectionError(f"NTRIP Handshake Failed: {response_str}")

