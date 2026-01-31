import asyncio
import aiofiles
from pathlib import Path
from typing import List
from src.ports.inputs import InputPort
from src.strategies.playback import PlaybackStrategy

class DirectoryAdapter(InputPort):
    """
    Input Adapter that reads NMEA files from a directory.
    Uses a Strategy to control playback speed.
    """
    def __init__(self, directory: Path, strategy: PlaybackStrategy, pattern: str = "*.nmea"):
        self.directory = directory
        self.strategy = strategy
        self.pattern = pattern

    async def start(self, queue: asyncio.Queue, stop_event: asyncio.Event) -> None:
        files = sorted(self.directory.glob(self.pattern), key=lambda p: p.name)
        
        for file_path in files:
            if stop_event.is_set():
                break
                
            async with aiofiles.open(file_path, mode='r') as f:
                async for line in f:
                    if stop_event.is_set():
                        break
                        
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 1. Apply timing strategy (wait if needed)
                    await self.strategy.wait(line)
                    
                    # 2. Push to queue
                    await queue.put(line)
        
        # Signal EOF? Or just stop?
        # Core likely waits for cancellation or sentinel.
        # Let's put a None sentinel to indicate end of all files.
        await queue.put(None)

    async def stop(self) -> None:
        pass
