"""TimescaleDB OutputPort adapter for VADASE real-time monitor.

Batch-buffers velocity and displacement rows and flushes via asyncpg executemany.
All write_velocity/write_displacement calls are fire-and-forget (flush via
asyncio.create_task) to preserve the 1 Hz real-time contract. write_event_detection
is synchronous -- exceptions propagate to the caller (DL-017).

Key design decisions encoded here:
  DL-001  asyncpg executemany batch buffering (not per-row pool.execute)
  DL-005  DSN from env vars (DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME)
  DL-006  ON CONFLICT (time, station_code) DO NOTHING for idempotent re-ingestion
  DL-007  5 s pool.acquire() timeout logged as pool_acquire_timeout
  DL-009  mid-flight flush error: batch restored to buffer front, never silent-drop
  DL-010  parser camelCase keys (vE, cq) -> SQL snake_case (v_east, quality)
  DL-013  pool min=2, max=10 sized to actual concurrent flush workload
  DL-014  _velocity_flushing/_displacement_flushing guards prevent concurrent flush
  DL-016  bounded buffers (buffer_max_size=10000): drop-oldest on overflow
  DL-017  hot path never blocks/raises on DB issues; event inserts are synchronous
  DL-018  camelCase->snake_case translation is positional in executemany tuples
"""

import asyncio
import os
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Optional, Tuple

import asyncpg
import structlog

logger = structlog.get_logger()

# Velocity INSERT includes quality column mapped from parser field 'cq'.
# Column order must match the positional tuple built in write_velocity (DL-010/DL-018).
_INSERT_VELOCITY = """
    INSERT INTO vadase_velocities
        (time, station_code, v_east, v_north, v_up, v_horizontal, quality)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (time, station_code) DO NOTHING
"""

# Displacement INSERT includes quality and displacement_source (migration 011).
_INSERT_DISPLACEMENT = """
    INSERT INTO vadase_displacements
        (time, station_code, d_east, d_north, d_up, d_horizontal, overall_completeness, quality, displacement_source)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    ON CONFLICT (time, station_code) DO NOTHING
"""

_INSERT_EVENT = """
    INSERT INTO vadase_events
        (station_code, detection_time, peak_velocity_horizontal,
         peak_displacement_horizontal, duration_seconds)
    VALUES ($1, $2, $3, $4, $5)
"""

# Type alias for a single buffered row tuple.
_VelRow = Tuple[Any, ...]
_DispRow = Tuple[Any, ...]


class TimescaleDBAdapter:
    """
    OutputPort adapter writing VADASE telemetry to TimescaleDB via asyncpg.

    Velocity and displacement rows are batch-buffered and flushed in bulk via
    executemany. Event detections are inserted immediately (rare writes).
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        batch_size: int = 100,
        flush_interval: float = 1.0,
        acquire_timeout: float = 5.0,
        buffer_max_size: int = 10_000,
    ) -> None:
        if dsn is None:
            user = os.environ.get("DB_USER", "pogf_user")
            password = os.environ.get("DB_PASSWORD", "pogf_password")
            host = os.environ.get("DB_HOST", "localhost")
            port = os.environ.get("DB_PORT", "5433")
            name = os.environ.get("DB_NAME", "pogf_db")
            dsn = f"postgresql://{user}:{password}@{host}:{port}/{name}"
        self._dsn = dsn
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._acquire_timeout = acquire_timeout
        self._buffer_max_size = buffer_max_size

        self._pool: Optional[asyncpg.Pool] = None
        self._flush_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._closing = False

        self._velocity_buffer: Deque[_VelRow] = deque()
        self._displacement_buffer: Deque[_DispRow] = deque()
        self._velocity_lock = asyncio.Lock()
        self._displacement_lock = asyncio.Lock()

        # Flushing guards prevent concurrent flush on the same buffer (DL-014).
        self._velocity_flushing = False
        self._displacement_flushing = False

        # Drop-oldest overflow counters (DL-016).
        self._velocity_dropped: int = 0
        self._displacement_dropped: int = 0
        self._last_overflow_log: float = 0.0

        self.log = logger.bind(component="timescaledb_adapter")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create the asyncpg pool and start the periodic flush background task.

        Lets asyncpg exceptions propagate so run_ingestor can fail-fast (DL-008).
        """
        # DSN host logged without password for operator diagnostics (DL-005/DL-008).
        dsn_parts = self._dsn.split("@")
        dsn_host = dsn_parts[-1] if "@" in self._dsn else "<no-host-in-dsn>"
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=2,
            max_size=10,
        )
        self._flush_task = asyncio.create_task(self._periodic_flush())
        self.log.info("connected", dsn_host=dsn_host)

    async def close(self) -> None:
        """Cancel periodic flush task, run a final flush, and close the pool."""
        self._closing = True
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_all()
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
        self.log.info("closed")

    # ------------------------------------------------------------------
    # OutputPort Protocol methods
    # ------------------------------------------------------------------

    async def write_velocity(self, station_id: str, data: Dict[str, Any]) -> None:
        """Buffer a velocity row. Flush is fire-and-forget when batch_size reached."""
        # Parser returns camelCase keys (vE, vN, vU, vH_magnitude, cq).
        # SQL columns are snake_case (v_east, v_north, v_up, v_horizontal, quality).
        # Translation is positional in this tuple (DL-010, DL-018).
        row: _VelRow = (
            data["timestamp"],
            station_id,
            data["vE"],
            data["vN"],
            data["vU"],
            data["vH_magnitude"],
            data["cq"],
        )
        async with self._velocity_lock:
            self._maybe_drop_oldest(self._velocity_buffer, "velocity")
            self._velocity_buffer.append(row)
            should_flush = (
                len(self._velocity_buffer) >= self._batch_size
                and not self._velocity_flushing
            )
        if should_flush:
            asyncio.create_task(self._flush_velocity())

    async def write_displacement(self, station_id: str, data: Dict[str, Any]) -> None:
        """Buffer a displacement row. Flush is fire-and-forget when batch_size reached."""
        row: _DispRow = (
            data["timestamp"],
            station_id,
            data["dE"],
            data["dN"],
            data["dU"],
            data["dH_magnitude"],
            data.get("overall_completeness"),
            data["cq"],
            data.get("displacement_source"),  # $9 -- RECEIVER | RECEIVER_SUSPECT | INTEGRATOR
        )
        async with self._displacement_lock:
            self._maybe_drop_oldest(self._displacement_buffer, "displacement")
            self._displacement_buffer.append(row)
            should_flush = (
                len(self._displacement_buffer) >= self._batch_size
                and not self._displacement_flushing
            )
        if should_flush:
            asyncio.create_task(self._flush_displacement())

    async def write_event_detection(
        self,
        station: str,
        detection_time: datetime,
        peak_velocity: float,
        peak_displacement: float,
        duration: float,
    ) -> None:
        """Immediately insert an event row. Exceptions propagate to caller (DL-017)."""
        if self._pool is None:
            self.log.error("write_event_called_before_connect")
            return
        async with self._pool.acquire(timeout=self._acquire_timeout) as conn:
            await conn.execute(
                _INSERT_EVENT,
                station,
                detection_time,
                peak_velocity,
                peak_displacement,
                duration,
            )
        self.log.info(
            "event_written",
            station=station,
            detection_time=detection_time,
            peak_velocity=peak_velocity,
        )

    # ------------------------------------------------------------------
    # Internal flush helpers
    # ------------------------------------------------------------------

    def _maybe_drop_oldest(self, buf: deque, buf_name: str) -> None:  # type: ignore[type-arg]
        """Drop oldest entry when buffer would exceed buffer_max_size (DL-016)."""
        if len(buf) >= self._buffer_max_size:
            buf.popleft()
            if buf_name == "velocity":
                self._velocity_dropped += 1
                dropped = self._velocity_dropped
            else:
                self._displacement_dropped += 1
                dropped = self._displacement_dropped
            now = time.monotonic()
            if now - self._last_overflow_log >= 1.0:
                self._last_overflow_log = now
                self.log.warning(
                    "buffer_overflow_drop",
                    buffer=buf_name,
                    dropped_total=dropped,
                    current_buffer_size=len(buf),
                )

    async def _flush_velocity(self) -> None:
        """Flush the velocity buffer via executemany. Restores batch on failure (DL-009)."""
        self._velocity_flushing = True
        batch: list[_VelRow] = []
        try:
            async with self._velocity_lock:
                batch = [self._velocity_buffer.popleft() for _ in range(len(self._velocity_buffer))]
            if not batch:
                return
            async with self._pool.acquire(timeout=self._acquire_timeout) as conn:  # type: ignore[union-attr]
                await conn.executemany(_INSERT_VELOCITY, batch)
        except asyncpg.exceptions.TooManyConnectionsError as exc:
            self.log.error(
                "pool_acquire_timeout",
                pool_idle=self._pool.get_idle_size() if self._pool else -1,
                pool_size=self._pool.get_size() if self._pool else -1,
                error=str(exc),
            )
            async with self._velocity_lock:
                self._velocity_buffer.extendleft(reversed(batch))
            raise
        except Exception as exc:
            self.log.error("flush_failed", buffer="velocity", batch_size=len(batch), error=str(exc))
            async with self._velocity_lock:
                # Restore batch to front of buffer, capped at buffer_max_size.
                combined = list(batch) + list(self._velocity_buffer)
                self._velocity_buffer.clear()
                for row in combined[: self._buffer_max_size]:
                    self._velocity_buffer.append(row)
            raise
        finally:
            self._velocity_flushing = False

    async def _flush_displacement(self) -> None:
        """Flush the displacement buffer via executemany. Restores batch on failure (DL-009)."""
        self._displacement_flushing = True
        batch: list[_DispRow] = []
        try:
            async with self._displacement_lock:
                batch = [self._displacement_buffer.popleft() for _ in range(len(self._displacement_buffer))]
            if not batch:
                return
            async with self._pool.acquire(timeout=self._acquire_timeout) as conn:  # type: ignore[union-attr]
                await conn.executemany(_INSERT_DISPLACEMENT, batch)
        except asyncpg.exceptions.TooManyConnectionsError as exc:
            self.log.error(
                "pool_acquire_timeout",
                pool_idle=self._pool.get_idle_size() if self._pool else -1,
                pool_size=self._pool.get_size() if self._pool else -1,
                error=str(exc),
            )
            async with self._displacement_lock:
                self._displacement_buffer.extendleft(reversed(batch))
            raise
        except Exception as exc:
            self.log.error(
                "flush_failed", buffer="displacement", batch_size=len(batch), error=str(exc)
            )
            async with self._displacement_lock:
                combined = list(batch) + list(self._displacement_buffer)
                self._displacement_buffer.clear()
                for row in combined[: self._buffer_max_size]:
                    self._displacement_buffer.append(row)
            raise
        finally:
            self._displacement_flushing = False

    async def _flush_all(self) -> None:
        """Flush both buffers (used by close() for a final drain)."""
        if self._velocity_buffer:
            try:
                await self._flush_velocity()
            except Exception:
                pass
        if self._displacement_buffer:
            try:
                await self._flush_displacement()
            except Exception:
                pass

    async def _periodic_flush(self) -> None:
        """Background task: flush both buffers every flush_interval seconds.

        On flush error: logs periodic_flush_error, backs off flush_interval*2,
        then continues. Never raises (cancellation via CancelledError is clean).
        """
        while not self._closing:
            await asyncio.sleep(self._flush_interval)
            try:
                await self._flush_all()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.log.error("periodic_flush_error", error=str(exc))
                await asyncio.sleep(self._flush_interval * 2)
