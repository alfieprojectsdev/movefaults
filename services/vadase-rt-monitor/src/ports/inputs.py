from typing import Protocol, Any
import asyncio

class InputPort(Protocol):
    """
    Port (Interface) for data ingestion.
    Adapters (TCP, File, Directory) must implement this.
    """
    async def start(self, queue: asyncio.Queue, stop_event: asyncio.Event) -> None:
        """
        Start producing data into the queue.
        Must respect stop_event to exit gracefully.
        """
        ...

    async def stop(self) -> None:
        """
        Signal the producer to stop.
        """
        ...
