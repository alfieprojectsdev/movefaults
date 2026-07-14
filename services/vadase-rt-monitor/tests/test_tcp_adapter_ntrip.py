"""Unit tests for TCPAdapter NTRIP handshake and reconnection logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.adapters.inputs.tcp import FatalConfigError, TCPAdapter


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
async def test_ntrip_v1_does_not_drain_data():
    """NTRIP 1.0 casters send 'ICY 200 OK' then stream immediately — no headers,
    no blank line. The handshake must consume ONLY the status line, or it eats
    the first NMEA sentences of every (re)connect."""
    readline_seq = [
        b"ICY 200 OK\r\n",
        b"$GNLVM,123519.00,020126,0.001,0.002,0.003*4F\r\n",  # DATA — must not be consumed
    ]
    mock_reader, mock_writer = _make_mocks(readline_seq)

    adapter = TCPAdapter(host="localhost", port=2101, station_id="TEST", mountpoint="TEST")
    adapter.reader = mock_reader
    adapter.writer = mock_writer

    await adapter._perform_handshake()  # must not raise

    written = b"".join(call.args[0] for call in mock_writer.write.call_args_list)
    assert b"GET /TEST HTTP/1.0" in written
    assert mock_reader.readline.call_count == 1, "v1 handshake must stop after the status line"


@pytest.mark.asyncio
async def test_http_response_drains_headers():
    """HTTP-style responses (NTRIP 2.0 / HTTP casters) carry headers terminated
    by a blank line; those must be drained before the data stream."""
    readline_seq = [
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: gnss/data\r\n",
        b"Server: NTRIP-Caster/2.0\r\n",
        b"\r\n",  # blank line terminates drain
    ]
    mock_reader, mock_writer = _make_mocks(readline_seq)

    adapter = TCPAdapter(host="localhost", port=2101, station_id="TEST", mountpoint="TEST")
    adapter.reader = mock_reader
    adapter.writer = mock_writer

    await adapter._perform_handshake()

    # All 4 lines consumed: status + 2 headers + blank terminator
    assert mock_reader.readline.call_count == 4


@pytest.mark.asyncio
async def test_handshake_sourcetable_raises_fatal():
    """SOURCETABLE response is a configuration error — raised as FatalConfigError."""
    readline_seq = [b"SOURCETABLE 200 OK\r\n"]
    mock_reader, mock_writer = _make_mocks(readline_seq)

    adapter = TCPAdapter(
        host="localhost", port=2101, station_id="TEST", mountpoint="NOMOUNT"
    )
    adapter.reader = mock_reader
    adapter.writer = mock_writer

    with pytest.raises(FatalConfigError, match="not an active stream"):
        await adapter._perform_handshake()


@pytest.mark.asyncio
async def test_handshake_401_raises_fatal():
    readline_seq = [b"HTTP/1.1 401 Unauthorized\r\n"]
    mock_reader, mock_writer = _make_mocks(readline_seq)

    adapter = TCPAdapter(
        host="localhost", port=2101, station_id="TEST", mountpoint="TEST",
        user="bad", password="creds",
    )
    adapter.reader = mock_reader
    adapter.writer = mock_writer

    with pytest.raises(FatalConfigError, match="unauthorized"):
        await adapter._perform_handshake()


@pytest.mark.asyncio
async def test_handshake_404_raises_fatal():
    readline_seq = [b"HTTP/1.1 404 Not Found\r\n"]
    mock_reader, mock_writer = _make_mocks(readline_seq)

    adapter = TCPAdapter(
        host="localhost", port=2101, station_id="TEST", mountpoint="MISSING"
    )
    adapter.reader = mock_reader
    adapter.writer = mock_writer

    with pytest.raises(FatalConfigError, match="not found"):
        await adapter._perform_handshake()


@pytest.mark.asyncio
async def test_fatal_config_error_stops_retry_loop():
    """A fatal config error (bad credentials) must stop the station, not retry
    forever — repeated bad-auth requests can get the shared caster account
    locked or the IP banned."""
    queue = asyncio.Queue()
    stop_event = asyncio.Event()

    connect_count = 0
    sleep_calls: list[float] = []

    async def _fake_open(*args, **kwargs):
        nonlocal connect_count
        connect_count += 1
        return _make_mocks([b"HTTP/1.1 401 Unauthorized\r\n"])

    async def _fake_sleep(secs):
        sleep_calls.append(secs)

    with (
        patch("asyncio.open_connection", side_effect=_fake_open),
        patch("asyncio.sleep", side_effect=_fake_sleep),
    ):
        adapter = TCPAdapter(
            host="localhost", port=2101, station_id="TEST", mountpoint="TEST",
            user="bad", password="creds",
        )
        await adapter.start(queue, stop_event)  # must return, not loop

    assert connect_count == 1, "fatal config error must not be retried"
    assert sleep_calls == [], "no backoff sleep after a fatal config error"


@pytest.mark.asyncio
async def test_handshake_timeout_is_retried():
    """A caster that accepts TCP but never responds must not hang the adapter
    forever: the handshake has its own timeout and falls into the retry path."""
    queue = asyncio.Queue()
    stop_event = asyncio.Event()

    sleep_calls: list[float] = []

    async def _hanging_readline(*args, **kwargs):
        await asyncio.sleep(30)
        return b""

    async def _fake_open(*args, **kwargs):
        mock_reader, mock_writer = _make_mocks([])
        mock_reader.readline.side_effect = _hanging_readline
        return mock_reader, mock_writer

    async def _fake_sleep(secs):
        sleep_calls.append(secs)
        stop_event.set()  # exit the loop after the first backoff

    with (
        patch("asyncio.open_connection", side_effect=_fake_open),
        patch.object(TCPAdapter, "HANDSHAKE_TIMEOUT", 0.05),
        patch("src.adapters.inputs.tcp.asyncio.sleep", side_effect=_fake_sleep),
    ):
        adapter = TCPAdapter(
            host="localhost", port=2101, station_id="TEST", mountpoint="TEST"
        )
        await asyncio.wait_for(adapter.start(queue, stop_event), timeout=5.0)

    assert len(sleep_calls) == 1, "handshake timeout must fall into the backoff/retry path"


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
        patch("random.uniform", side_effect=lambda a, b: b),  # deterministic: take the max
    ):
        adapter = TCPAdapter(host="localhost", port=2101, station_id="TEST")
        await adapter.start(queue, stop_event)

    assert len(sleep_calls) >= 2
    # First delay ≈ 5 s, second ≈ 10 s (doubled)
    assert sleep_calls[0] == pytest.approx(5.0, abs=0.1)
    assert sleep_calls[1] == pytest.approx(10.0, abs=0.1)


@pytest.mark.asyncio
async def test_backoff_jitter_spreads_across_window():
    """Full jitter: the delay is drawn from [base, backoff] so 35 stations
    don't reconnect in lockstep after a shared caster outage."""
    queue = asyncio.Queue()
    stop_event = asyncio.Event()

    connect_count = 0
    uniform_args: list[tuple[float, float]] = []

    async def _fake_open(*args, **kwargs):
        nonlocal connect_count
        connect_count += 1
        if connect_count >= 3:
            stop_event.set()
        raise OSError("connection refused")

    def _spy_uniform(a, b):
        uniform_args.append((a, b))
        return a

    with (
        patch("asyncio.open_connection", side_effect=_fake_open),
        patch("asyncio.sleep", new=AsyncMock()),
        patch("src.adapters.inputs.tcp.random.uniform", side_effect=_spy_uniform),
    ):
        adapter = TCPAdapter(host="localhost", port=2101, station_id="TEST")
        await adapter.start(queue, stop_event)

    # Second retry draws from the widened window [base, 2*base]
    assert uniform_args[1] == (5.0, 10.0)


@pytest.mark.asyncio
async def test_backoff_resets_on_successful_connection():
    """Backoff resets to base value after a successful connection."""
    queue = asyncio.Queue()
    stop_event = asyncio.Event()

    connect_count = 0
    sleep_calls: list[float] = []

    async def _fake_open(*args, **kwargs):
        nonlocal connect_count
        connect_count += 1
        if connect_count == 1:
            raise OSError("first attempt fails")
        mock_reader, mock_writer = _make_mocks(
            [b"ICY 200 OK\r\n"], read_chunks=[b""]
        )
        stop_event.set()
        return mock_reader, mock_writer

    async def _fake_sleep(secs):
        sleep_calls.append(secs)

    with (
        patch("asyncio.open_connection", side_effect=_fake_open),
        patch("asyncio.sleep", side_effect=_fake_sleep),
        patch("random.uniform", side_effect=lambda a, b: a),
    ):
        adapter = TCPAdapter(
            host="localhost", port=2101, station_id="TEST", mountpoint="TEST"
        )
        await adapter.start(queue, stop_event)

    # First sleep is the retry after failure (5 s base)
    assert sleep_calls[0] == pytest.approx(5.0, abs=0.1)
    # connect_count == 2 means we connected successfully on second attempt
    assert connect_count == 2
