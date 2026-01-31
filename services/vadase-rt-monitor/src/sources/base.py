from typing import Protocol, AsyncIterator

class DataSource(Protocol):
    """
    Interface for NMEA data sources (TCP Stream or File).
    """
    async def connect(self) -> None:
        """Prepare the connection (open socket or file handle)."""
        ...

    async def close(self) -> None:
        """Clean up resources."""
        ...

    def __aiter__(self) -> AsyncIterator[str]:
        """Async iterator yielding raw NMEA lines."""
        ...
