import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import structlog
from structlog.testing import capture_logs
from src.adapters.inputs.tcp import TCPAdapter

@pytest.mark.asyncio
async def test_tcp_adapter_dos_protection():
    """
    Test that the TCP adapter prevents unbounded buffer growth.
    """
    queue = asyncio.Queue()
    stop_event = asyncio.Event()

    # Create a mock reader that returns chunks of data without newlines
    # We want to exceed a reasonable buffer limit (e.g. 1MB).
    chunk_size = 4096
    total_chunks = 500 # ~2MB
    data_chunks = [b"A" * chunk_size] * total_chunks

    mock_reader = AsyncMock()
    # side_effect to yield chunks. Last one waits forever to simulate open connection
    async def side_effect(*args, **kwargs):
        if data_chunks:
            # Yield quickly to fill buffer
            return data_chunks.pop(0)
        # Keep connection open but idle
        await asyncio.sleep(10)
        return b""

    mock_reader.read.side_effect = side_effect
    mock_reader.readline.return_value = b"ICY 200 OK\r\n" # For handshake

    # Mock StreamWriter correctly
    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.wait_closed = AsyncMock()
    mock_writer.write = MagicMock()
    mock_writer.close = MagicMock()

    with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
        with capture_logs() as cap_logs:
            adapter = TCPAdapter(
                host="localhost",
                port=2101,
                station_id="TEST",
                mountpoint="TEST",
            )

            # Start the adapter
            task = asyncio.create_task(adapter.start(queue, stop_event))

            # Wait enough time for buffer to fill up
            await asyncio.sleep(1)

            # Stop the adapter to clean up
            stop_event.set()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.TimeoutError:
                task.cancel()
            except Exception:
                pass

            # Verify logs
            overflow_logs = [log for log in cap_logs if log.get("event") == "buffer_overflow"]

            assert len(overflow_logs) > 0, "Did not detect buffer overflow (Vulnerability reproduced)"

            # Check for disconnect/reconnect attempt log
            # Since we break the inner loop, we should see "reconnecting_in" or "connection_error" depending on flow
            # In our case, we break, then cleanup, then retry delay
            reconnect_logs = [log for log in cap_logs if log.get("event") == "reconnecting_in"]
            # It might not happen if stop_event is set immediately after sleep(1) and the loop checks stop_event.
            # But the buffer overflow break happens inside the inner loop.
            # After break, it calls cleanup, then checks stop_event.
            # If stop_event is NOT set yet, it sleeps.
            # We set stop_event after sleep(1). So likely it entered sleep(5) or checked stop_event.

            # Anyway, the primary assertion is overflow_logs.
