"""
The /health schema guard (field_ops/schema_check.py).

What must hold, because the 2026-09-23 outage is what happens when it doesn't:
a database behind the code makes /health answer 503, so Render refuses the
deploy. Just as important are the cases that must NOT fail: a rollback, an
unreachable database, and SQLite, none of which a health check should turn
into a restart loop.
"""

import re
from pathlib import Path

import pytest
from field_ops import schema_check
from field_ops.database import get_db
from field_ops.main import app
from httpx import ASGITransport, AsyncClient

HEAD = frozenset({"fo008"})
KNOWN = frozenset({"fo001", "fo002", "fo007", "fo008"})


# --- the pure decision ---------------------------------------------------------


def test_current_when_database_is_at_head():
    s = schema_check.classify(HEAD, KNOWN, frozenset({"fo008"}))
    assert s.state == "current" and not s.blocks_traffic


def test_behind_when_database_is_at_an_older_known_revision():
    # The 2026-09-23 shape exactly: code at fo008, database left at fo007.
    s = schema_check.classify(HEAD, KNOWN, frozenset({"fo007"}))
    assert s.state == "behind" and s.blocks_traffic
    assert "upgrade head" in s.detail


def test_behind_when_nothing_was_ever_migrated():
    s = schema_check.classify(HEAD, KNOWN, frozenset())
    assert s.state == "behind" and s.blocks_traffic


def test_rollback_does_not_block_traffic():
    # Database migrated to a revision this (older) code has never heard of.
    s = schema_check.classify(HEAD, KNOWN, frozenset({"fo009"}))
    assert s.state == "unrecognised" and not s.blocks_traffic


# --- the migration files the image ships ----------------------------------------


def test_real_migrations_have_exactly_one_head():
    schema_check._script_directory.cache_clear()
    heads = schema_check.expected_heads()
    assert len(heads) == 1, f"migration tree has diverged into several heads: {heads}"
    assert heads <= schema_check.known_revisions()


def test_missing_migrations_refuse_to_start(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_OPS_MIGRATIONS_DIR", str(tmp_path / "nowhere"))
    schema_check._script_directory.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="migrations not found"):
            schema_check.expected_heads()
    finally:
        schema_check._script_directory.cache_clear()


def test_dockerfile_ships_the_migrations():
    # The runtime check is only as good as the files it reads. If the image stops
    # copying them, startup fails; this catches it before a deploy does.
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    assert re.search(
        r"^COPY services/field-ops/migrations/ \./migrations/$",
        dockerfile.read_text(),
        re.M,
    )


# --- the endpoint -------------------------------------------------------------------


@pytest.fixture
def health_client(monkeypatch):
    schema_check.reset_cache()

    async def no_db():
        yield None

    app.dependency_overrides[get_db] = no_db

    def with_status(status):
        async def fake(_session):
            return status

        monkeypatch.setattr(schema_check, "current_status", fake)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield with_status
    app.dependency_overrides.pop(get_db, None)
    schema_check.reset_cache()


@pytest.mark.asyncio
async def test_health_is_503_when_database_is_behind(health_client):
    status = schema_check.classify(HEAD, KNOWN, frozenset({"fo007"}))
    async with health_client(status) as c:
        r = await c.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "schema_behind"
    assert body["schema"]["expected"] == ["fo008"]
    assert body["schema"]["database"] == ["fo007"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        schema_check.classify(HEAD, KNOWN, frozenset({"fo008"})),
        schema_check.classify(HEAD, KNOWN, frozenset({"fo009"})),
        schema_check.SchemaStatus("unknown", HEAD, detail="database not reachable"),
    ],
    ids=["current", "rollback", "unreachable"],
)
async def test_health_is_200_otherwise(health_client, status):
    async with health_client(status) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["schema"]["state"] == status.state


@pytest.mark.asyncio
async def test_sqlite_session_reports_unknown_not_behind(db_session):
    # The unit-test database is SQLite. It must read as "cannot tell", never as
    # "behind", or every existing test that touches /health would start failing.
    schema_check.reset_cache()
    status = await schema_check.current_status(db_session)
    schema_check.reset_cache()
    assert status.state == "unknown"
    assert not status.blocks_traffic


# --- permanent vs transient database errors -------------------------------------------
#
# Review of #249: a catch-all turned a wrong password into "unknown" -> 200, so a
# deploy with dead credentials took traffic and 500ed on every database route.


class InvalidPasswordError(Exception):
    """Stands in for asyncpg's class of the same name; matched by name."""


class _Wrapper(Exception):
    def __init__(self, orig):
        super().__init__("wrapped")
        self.orig = orig


class _PgSession:
    class bind:  # noqa: N801 - mimics AsyncSession.bind
        class dialect:  # noqa: N801
            name = "postgresql"

    def __init__(self, exc):
        self._exc = exc

    async def execute(self, *_a, **_k):
        raise self._exc


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        InvalidPasswordError("password authentication failed"),
        _Wrapper(InvalidPasswordError("wrapped by SQLAlchemy")),
    ],
    ids=["raw", "wrapped"],
)
async def test_rejected_credentials_block_traffic(exc):
    schema_check.reset_cache()
    status = await schema_check.current_status(_PgSession(exc))
    schema_check.reset_cache()
    assert status.state == "misconfigured"
    assert status.blocks_traffic
    assert "InvalidPasswordError" in status.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [TimeoutError(), ConnectionRefusedError(), OSError("dns")])
async def test_transient_errors_do_not_block_traffic(exc):
    schema_check.reset_cache()
    status = await schema_check.current_status(_PgSession(exc))
    schema_check.reset_cache()
    assert status.state == "unknown"
    assert not status.blocks_traffic


@pytest.mark.asyncio
async def test_health_names_the_misconfiguration(health_client):
    status = schema_check.SchemaStatus("misconfigured", HEAD, detail="InvalidPasswordError")
    async with health_client(status) as c:
        r = await c.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "database_misconfigured"
