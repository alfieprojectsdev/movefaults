import asyncio
import os
from datetime import datetime
from typing import Optional
import asyncpg
from dotenv import load_dotenv

load_dotenv()

class DatabaseWriter:
    def __init__(self, batch_size: int = 100, flush_interval: float = 1.0):
        self.dsn = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        self.pool = None
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        self._velocity_buffer = []
        self._displacement_buffer = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._closing = False
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.dsn, min_size=5, max_size=20)
        self._closing = False
        self._flush_task = asyncio.create_task(self._periodic_flush())
    
    async def close(self):
        self._closing = True
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush of any remaining data
        await self.flush_all()

        if self.pool:
            await self.pool.close()

    async def _periodic_flush(self):
        """Background task to flush buffers periodically"""
        while not self._closing:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush_all()
            except asyncio.CancelledError:
                break
            except Exception:
                # In a production system, we should log this
                pass

    async def flush_all(self):
        """Flush all buffers to the database"""
        await asyncio.gather(
            self._flush_velocity(),
            self._flush_displacement()
        )

    async def _flush_velocity(self):
        """Internal method to flush velocity buffer"""
        if not self._velocity_buffer:
            return

        async with self._lock:
            batch = self._velocity_buffer
            self._velocity_buffer = []

        if batch and self.pool:
            async with self.pool.acquire() as conn:
                await conn.executemany('''
                    INSERT INTO vadase_velocity (time, station, vN, vE, vU, quality)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (time, station) DO NOTHING
                ''', batch)

    async def _flush_displacement(self):
        """Internal method to flush displacement buffer"""
        if not self._displacement_buffer:
            return

        async with self._lock:
            batch = self._displacement_buffer
            self._displacement_buffer = []

        if batch and self.pool:
            async with self.pool.acquire() as conn:
                await conn.executemany('''
                    INSERT INTO vadase_displacement (time, station, dN, dE, dU, quality)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (time, station) DO NOTHING
                ''', batch)

    async def write_velocity(self, station_id, data):
        """Buffer velocity measurement"""
        async with self._lock:
            self._velocity_buffer.append((
                data['timestamp'], station_id,
                data['vN'], data['vE'], data['vU'], data['quality']
            ))

            if len(self._velocity_buffer) >= self.batch_size:
                # Trigger immediate flush if batch size reached
                asyncio.create_task(self._flush_velocity())
    
    async def write_displacement(self, station_id, data):
        """Buffer displacement measurement"""
        async with self._lock:
            self._displacement_buffer.append((
                data['timestamp'], station_id,
                data['dN'], data['dE'], data['dU'], data['quality']
            ))

            if len(self._displacement_buffer) >= self.batch_size:
                # Trigger immediate flush if batch size reached
                asyncio.create_task(self._flush_displacement())

    async def write_event_detection(self, station, detection_time, peak_velocity, peak_displacement, duration):
        """Insert event detection record (immediate insert as these are rare)"""
        if not self.pool:
            return

        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO event_detections (detection_time, station, peak_velocity_horizontal, peak_displacement_horizontal, duration_seconds)
                VALUES ($1, $2, $3, $4, $5)
            ''', detection_time, station, peak_velocity, peak_displacement, duration)
