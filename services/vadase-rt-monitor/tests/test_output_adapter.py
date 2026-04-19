"""Tests for TimescaleDBAdapter and NullOutputPort.

TimescaleDBAdapter tests use asyncpg mock to avoid a live database.
NullOutputPort tests confirm all methods are callable and return None.

CI-M-003-002 scenarios covered:
  (a) connect() creates pool and starts periodic flush task
  (b) connect() propagates asyncpg.CannotConnectNowError (no silent fallback)
  (c) write_velocity() buffers tuple and does NOT flush when below batch_size
  (d) write_velocity() triggers fire-and-forget flush task at batch_size threshold
  (e) write_velocity() with buffer_max_size reached drops oldest tuple
  (f) write_displacement() same buffer-and-flush behaviour
  (g) write_event_detection() performs immediate insert and propagates exceptions
  (h) mid-flight flush failure restores batch to buffer front (no silent drop)
  (i) pool acquire timeout logs pool_acquire_timeout with pool metrics
  (j) close() runs final flush and closes pool
  (k) ON CONFLICT DO NOTHING SQL present in executemany calls
  (l) snake_case SQL columns paired with camelCase dict keys at correct positions
"""

import asyncio
import pytest
from collections import deque
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg

from src.adapters.outputs.null import NullOutputPort
from src.adapters.outputs.timescaledb import (
    TimescaleDBAdapter,
    _INSERT_VELOCITY,
    _INSERT_DISPLACEMENT,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _sample_vel_data(ts=None):
    return {
        "timestamp": ts or datetime(2025, 10, 6, 15, 0, 1, tzinfo=timezone.utc),
        "vE": 0.001,
        "vN": 0.002,
        "vU": -0.001,
        "vH_magnitude": 0.00224,
        "cq": 0.95,
    }


def _sample_disp_data(ts=None):
    return {
        "timestamp": ts or datetime(2025, 10, 6, 15, 0, 1, tzinfo=timezone.utc),
        "dE": 0.002,
        "dN": 0.003,
        "dU": 0.001,
        "dH_magnitude": 0.0036,
        "overall_completeness": 0.98,
        "cq": 0.92,
    }


def _make_mock_pool():
    """Create a mock asyncpg pool with async context manager for acquire()."""
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    pool.close = AsyncMock()
    pool.get_idle_size = MagicMock(return_value=1)
    pool.get_size = MagicMock(return_value=2)
    return pool, conn


# ---------------------------------------------------------------------------
# NullOutputPort
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_null_output_port_lifecycle():
    port = NullOutputPort()
    await port.connect()
    await port.close()


@pytest.mark.asyncio
async def test_null_output_port_write_velocity():
    port = NullOutputPort()
    result = await port.write_velocity("BOST", _sample_vel_data())
    assert result is None


@pytest.mark.asyncio
async def test_null_output_port_write_displacement():
    port = NullOutputPort()
    result = await port.write_displacement("BOST", _sample_disp_data())
    assert result is None


@pytest.mark.asyncio
async def test_null_output_port_write_event():
    port = NullOutputPort()
    result = await port.write_event_detection(
        "BOST", datetime.now(timezone.utc), 25.3, 10.1, 12.5
    )
    assert result is None


# ---------------------------------------------------------------------------
# (a) connect() creates pool and starts periodic flush task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_creates_pool_and_starts_flush_task():
    mock_pool, _ = _make_mock_pool()
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", flush_interval=60.0)

    with patch("asyncpg.create_pool", AsyncMock(return_value=mock_pool)):
        await adapter.connect()

    assert adapter._pool is mock_pool
    assert adapter._flush_task is not None
    assert not adapter._flush_task.done()

    # Cleanup: cancel background task
    adapter._flush_task.cancel()
    try:
        await adapter._flush_task
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# (b) connect() propagates asyncpg.CannotConnectNowError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_propagates_cannot_connect_error():
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db")

    with patch(
        "asyncpg.create_pool",
        AsyncMock(side_effect=asyncpg.CannotConnectNowError()),
    ):
        with pytest.raises(asyncpg.CannotConnectNowError):
            await adapter.connect()

    # Pool must remain None -- no silent fallback.
    assert adapter._pool is None


# ---------------------------------------------------------------------------
# (c) write_velocity() buffers tuple and does NOT flush when below batch_size
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_velocity_buffers_below_batch_size():
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=100)
    mock_pool, _ = _make_mock_pool()
    adapter._pool = mock_pool

    await adapter.write_velocity("BOST", _sample_vel_data())

    assert len(adapter._velocity_buffer) == 1
    assert not adapter._velocity_flushing


# ---------------------------------------------------------------------------
# (d) write_velocity() triggers flush task at batch_size threshold
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_velocity_triggers_flush_at_batch_size():
    batch_size = 3
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=batch_size)
    mock_pool, conn = _make_mock_pool()
    adapter._pool = mock_pool

    # Fill to batch_size -- last write should trigger a flush task.
    for _ in range(batch_size):
        await adapter.write_velocity("BOST", _sample_vel_data())

    # Allow the fire-and-forget task to run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    conn.executemany.assert_awaited()
    call_args = conn.executemany.call_args
    sql = call_args.args[0]
    assert "ON CONFLICT" in sql


# ---------------------------------------------------------------------------
# (e) buffer overflow: drops oldest tuple and increments counter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_velocity_overflow_drops_oldest():
    max_size = 5
    adapter = TimescaleDBAdapter(
        dsn="postgresql://fake/db", batch_size=1000, buffer_max_size=max_size
    )
    mock_pool, _ = _make_mock_pool()
    adapter._pool = mock_pool
    # Disable flushing to observe buffer behaviour purely.
    adapter._velocity_flushing = True

    # Insert max_size rows to fill the buffer.
    for i in range(max_size):
        data = _sample_vel_data(ts=datetime(2025, 1, 1, 0, 0, i, tzinfo=timezone.utc))
        data["vE"] = float(i)
        await adapter.write_velocity("BOST", data)

    # Insert one more -- should drop oldest.
    overflow_data = _sample_vel_data(ts=datetime(2025, 1, 1, 0, 1, 39, tzinfo=timezone.utc))
    overflow_data["vE"] = 99.0
    await adapter.write_velocity("BOST", overflow_data)

    assert len(adapter._velocity_buffer) == max_size
    assert adapter._velocity_dropped == 1
    # Oldest (vE=0.0) should be gone; newest (vE=99.0) should be present.
    rows = list(adapter._velocity_buffer)
    v_east_values = [r[2] for r in rows]
    assert 0.0 not in v_east_values
    assert 99.0 in v_east_values


# ---------------------------------------------------------------------------
# (f) write_displacement() same buffer-and-flush behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_displacement_buffers_and_flushes():
    batch_size = 2
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=batch_size)
    mock_pool, conn = _make_mock_pool()
    adapter._pool = mock_pool

    for _ in range(batch_size):
        await adapter.write_displacement("BOST", _sample_disp_data())

    await asyncio.sleep(0)
    await asyncio.sleep(0)

    conn.executemany.assert_awaited()
    sql = conn.executemany.call_args.args[0]
    assert "vadase_displacements" in sql
    assert "ON CONFLICT" in sql


# ---------------------------------------------------------------------------
# (g) write_event_detection() immediate insert; exceptions propagate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_event_detection_immediate_insert():
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db")
    mock_pool, conn = _make_mock_pool()
    adapter._pool = mock_pool

    detection_time = datetime(2025, 10, 6, 15, 0, 5, tzinfo=timezone.utc)
    await adapter.write_event_detection("BOST", detection_time, 28.5, 12.3, 15.0)

    conn.execute.assert_awaited_once()
    args = conn.execute.call_args.args
    assert args[1] == "BOST"
    assert args[3] == pytest.approx(28.5)  # peak_velocity_horizontal


@pytest.mark.asyncio
async def test_write_event_detection_propagates_exception():
    """write_event_detection is synchronous -- exceptions must propagate (DL-017)."""
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db")
    mock_pool, conn = _make_mock_pool()
    conn.execute = AsyncMock(side_effect=asyncpg.PostgresError())
    adapter._pool = mock_pool

    with pytest.raises(asyncpg.PostgresError):
        await adapter.write_event_detection(
            "BOST", datetime.now(timezone.utc), 10.0, 5.0, 8.0
        )


# ---------------------------------------------------------------------------
# (h) mid-flight flush failure restores batch to buffer front
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_flush_failure_restores_batch_to_buffer():
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=1000)
    mock_pool, conn = _make_mock_pool()
    conn.executemany = AsyncMock(side_effect=asyncpg.PostgresError("db gone"))
    adapter._pool = mock_pool

    # Pre-fill buffer with 3 rows.
    for i in range(3):
        data = _sample_vel_data(ts=datetime(2025, 1, 1, 0, 0, i, tzinfo=timezone.utc))
        await adapter.write_velocity("BOST", data)

    assert len(adapter._velocity_buffer) == 3

    # Manually trigger a flush that will fail.
    with pytest.raises(asyncpg.PostgresError):
        await adapter._flush_velocity()

    # Rows must be restored -- silent drop is forbidden while pool is reachable (DL-009).
    assert len(adapter._velocity_buffer) == 3
    assert not adapter._velocity_flushing  # guard must be cleared in finally


# ---------------------------------------------------------------------------
# (i) pool acquire timeout logs pool_acquire_timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pool_acquire_timeout_logs_metrics():
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=1000)

    mock_pool = MagicMock()
    mock_pool.get_idle_size = MagicMock(return_value=0)
    mock_pool.get_size = MagicMock(return_value=10)

    # Simulate acquire raising TooManyConnectionsError (closest to PoolTimeout in asyncpg).
    conn_ctx = MagicMock()
    conn_ctx.__aenter__ = AsyncMock(
        side_effect=asyncpg.exceptions.TooManyConnectionsError()
    )
    conn_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.acquire = MagicMock(return_value=conn_ctx)
    adapter._pool = mock_pool

    # Pre-fill buffer with one row.
    data = _sample_vel_data()
    await adapter.write_velocity("BOST", data)
    # Clear the buffer's lock contention; manually prime for flush.
    adapter._velocity_flushing = False

    with patch.object(adapter.log, "error") as mock_error:
        with pytest.raises(asyncpg.exceptions.TooManyConnectionsError):
            await adapter._flush_velocity()

        error_calls = [str(c) for c in mock_error.call_args_list]
        assert any("pool_acquire_timeout" in c for c in error_calls)


# ---------------------------------------------------------------------------
# (j) close() runs final flush and closes pool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_close_runs_final_flush_and_closes_pool():
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", flush_interval=60.0)
    mock_pool, conn = _make_mock_pool()
    adapter._pool = mock_pool
    adapter._flush_task = asyncio.create_task(asyncio.sleep(9999))

    # Place one row in the buffer to verify final flush.
    await adapter.write_velocity("BOST", _sample_vel_data())
    assert len(adapter._velocity_buffer) == 1

    await adapter.close()

    mock_pool.close.assert_awaited_once()
    # Buffer should be drained by the final _flush_all.
    assert len(adapter._velocity_buffer) == 0


# ---------------------------------------------------------------------------
# (k) ON CONFLICT DO NOTHING SQL in executemany INSERT statements
# ---------------------------------------------------------------------------

def test_insert_sql_has_on_conflict_velocity():
    assert "ON CONFLICT" in _INSERT_VELOCITY
    assert "DO NOTHING" in _INSERT_VELOCITY


def test_insert_sql_has_on_conflict_displacement():
    assert "ON CONFLICT" in _INSERT_DISPLACEMENT
    assert "DO NOTHING" in _INSERT_DISPLACEMENT


# ---------------------------------------------------------------------------
# (l) camelCase dict keys -> snake_case SQL columns at correct positional indices
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_velocity_positional_mapping():
    """Verify camelCase parser keys map to correct SQL positional parameters (DL-018)."""
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=1000)
    mock_pool, _ = _make_mock_pool()
    adapter._pool = mock_pool
    adapter._velocity_flushing = True  # Prevent auto-flush; inspect buffer directly.

    ts = datetime(2025, 10, 6, 15, 0, 1, tzinfo=timezone.utc)
    data = {
        "timestamp": ts,
        "vE": 0.111,
        "vN": 0.222,
        "vU": 0.333,
        "vH_magnitude": 0.444,
        "cq": 0.888,
    }
    await adapter.write_velocity("PBIS", data)

    row = adapter._velocity_buffer[0]
    # Positional mapping: (time, station_code, v_east, v_north, v_up, v_horizontal, quality)
    assert row[0] == ts           # $1 time
    assert row[1] == "PBIS"       # $2 station_code
    assert row[2] == 0.111        # $3 v_east <- vE
    assert row[3] == 0.222        # $4 v_north <- vN
    assert row[4] == 0.333        # $5 v_up <- vU
    assert row[5] == 0.444        # $6 v_horizontal <- vH_magnitude
    assert row[6] == 0.888        # $7 quality <- cq


@pytest.mark.asyncio
async def test_write_displacement_positional_mapping():
    """Verify camelCase parser keys map to correct SQL positional parameters (DL-018)."""
    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=1000)
    mock_pool, _ = _make_mock_pool()
    adapter._pool = mock_pool
    adapter._displacement_flushing = True

    ts = datetime(2025, 10, 6, 15, 0, 2, tzinfo=timezone.utc)
    data = {
        "timestamp": ts,
        "dE": 0.010,
        "dN": 0.020,
        "dU": 0.030,
        "dH_magnitude": 0.040,
        "overall_completeness": 0.99,
        "cq": 0.77,
    }
    await adapter.write_displacement("BOST", data)

    row = adapter._displacement_buffer[0]
    # Positional: (time, station_code, d_east, d_north, d_up, d_horizontal, overall_completeness, quality)
    assert row[0] == ts           # $1 time
    assert row[1] == "BOST"       # $2 station_code
    assert row[2] == 0.010        # $3 d_east <- dE
    assert row[3] == 0.020        # $4 d_north <- dN
    assert row[4] == 0.030        # $5 d_up <- dU
    assert row[5] == 0.040        # $6 d_horizontal <- dH_magnitude
    assert row[6] == 0.99         # $7 overall_completeness
    assert row[7] == 0.77         # $8 quality <- cq
