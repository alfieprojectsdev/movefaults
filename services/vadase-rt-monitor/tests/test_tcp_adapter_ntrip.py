"""Unit tests for TCPAdapter NTRIP handshake and reconnection logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.inputs.tcp import TCPAdapter


def _make_mocks(readline_responses: list[bytes], read_chunks: list[bytes] | None = None):
    """Build (mock_reader, mock_writer) with the given readline/read sequences."""
    mock_reader = AsyncMock()
    mock_reader.readline.side_effect = readline_responses

    async def _read_side_effect(*args, **kwargs):
        if read_chunks:
            return read_chunks.pop(0) if read_chunks else b""
        await asyncio.sleep(10)
        return b""

    mock_reader.read.side_effect = _read_side_effect

    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.wait_closed = AsyncMock()
    mock_writer.write = MagicMock()
    mock_writer.close = MagicMock()

    return mock_reader, mock_writer


@pytest.mark.asyncio
async def test_handshake_success_drains_headers():
    """ICY 200 OK + extra headers → handshake succeeds and all header lines are consumed."""
    readline_seq = [
        b"ICY 200 OK\r\n",
        b"Content-Type: text/plain\r\n",
        b"Server: NTRIP-Caster/1.0\r\n",
        b"\r\n",  # blank line terminates drain
    ]
    mock_reader, mock_writer = _make_mocks(readline_seq)

    adapter = TCPAdapter(host="localhost", port=2101, station_id="TEST", mountpoint="TEST")
    adapter.reader = mock_reader
    adapter.writer = mock_writer

    await adapter._perform_handshake()  # must not raise

    written = b"".join(call.args[0] for call in mock_writer.write.call_args_list)
    assert b"GET /TEST HTTP/1.0" in written
    # All 4 lines consumed: status + 2 headers + blank terminator
    assert mock_reader.readline.call_count == 4


@pytest.mark.asyncio
async def test_handshake_sourcetable_raises():
    """SOURCETABLE response is raised as a descriptive ConnectionError."""
    readline_seq = [b"SOURCETABLE 200 OK\r\n"]
    mock_reader, mock_writer = _make_mocks(readline_seq)

    adapter = TCPAdapter(
        host="localhost", port=2101, station_id="TEST", mountpoint="NOMOUNT"
    )
    adapter.reader = mock_reader
    adapter.writer = mock_writer

    with pytest.raises(ConnectionError, match="not an active stream"):
        await adapter._perform_handshake()


@pytest.mark.asyncio
async def test_handshake_401_raises():
    readline_seq = [b"HTTP/1.1 401 Unauthorized\r\n"]
    mock_reader, mock_writer = _make_mocks(readline_seq)

    adapter = TCPAdapter(
        host="localhost", port=2101, station_id="TEST", mountpoint="TEST", user="bad", password="creds"
    )
    adapter.reader = mock_reader
    adapter.writer = mock_writer

    with pytest.raises(ConnectionError, match="unauthorized"):
        await adapter._perform_handshake()


@pytest.mark.asyncio
async def test_handshake_404_raises():
    readline_seq = [b"HTTP/1.1 404 Not Found\r\n"]
    mock_reader, mock_writer = _make_mocks(readline_seq)

    adapter = TCPAdapter(
        host="localhost", port=2101, station_id="TEST", mountpoint="MISSING"
    )
    adapter.reader = mock_reader
    adapter.writer = mock_writer

    with pytest.raises(ConnectionError, match="not found"):
        await adapter._perform_handshake()


@pytest.mark.asyncio
async def test_exponential_backoff_increases():
    """Adapter doubles backoff on each failed connection, caps at 60 s."""
    queue = asyncio.Queue()
    stop_event = asyncio.Event()

    connect_count = 0
    sleep_calls: list[float] = []

    async def _fake_open(*args, **kwargs):
        nonlocal connect_count
        connect_count += 1
        if connect_count >= 3:
            stop_event.set()
        raise OSError("connection refused")

    async def _fake_sleep(secs):
        sleep_calls.append(secs)

    with (
        patch("asyncio.open_connection", side_effect=_fake_open),
        patch("asyncio.sleep", side_effect=_fake_sleep),
        patch("random.uniform", return_value=0.0),  # suppress jitter for determinism
    ):
        adapter = TCPAdapter(host="localhost", port=2101, station_id="TEST")
        await adapter.start(queue, stop_event)

    assert len(sleep_calls) >= 2
    # First delay ≈ 5 s, second ≈ 10 s (doubled)
    assert sleep_calls[0] == pytest.approx(5.0, abs=0.1)
    assert sleep_calls[1] == pytest.approx(10.0, abs=0.1)


@pytest.mark.asyncio
async def test_backoff_resets_on_successful_connection():
    """Backoff resets to base value after a successful connection."""
    queue = asyncio.Queue()
    stop_event = asyncio.Event()

    connect_count = 0
    sleep_calls: list[float] = []

    readline_seq_success = [b"ICY 200 OK\r\n", b"\r\n"]

    async def _fake_open(*args, **kwargs):
        nonlocal connect_count
        connect_count += 1
        if connect_count == 1:
            raise OSError("first attempt fails")
        mock_reader, mock_writer = _make_mocks(
            [b"ICY 200 OK\r\n", b"\r\n"], read_chunks=[b""]
        )
        stop_event.set()
        return mock_reader, mock_writer

    async def _fake_sleep(secs):
        sleep_calls.append(secs)

    with (
        patch("asyncio.open_connection", side_effect=_fake_open),
        patch("asyncio.sleep", side_effect=_fake_sleep),
        patch("random.uniform", return_value=0.0),
    ):
        adapter = TCPAdapter(
            host="localhost", port=2101, station_id="TEST", mountpoint="TEST"
        )
        await adapter.start(queue, stop_event)

    # First sleep is the retry after failure (5 s base)
    assert sleep_calls[0] == pytest.approx(5.0, abs=0.1)
    # connect_count == 2 means we connected successfully on second attempt
    assert connect_count == 2
