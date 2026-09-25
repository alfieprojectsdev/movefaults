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

    app.dependency_overrides[schema_check.get_health_db] = no_db

    def with_status(status):
        async def fake(_session):
            return status

        monkeypatch.setattr(schema_check, "current_status", fake)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield with_status
    app.dependency_overrides.pop(schema_check.get_health_db, None)
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
        schema_check.SchemaStatus("not_applicable", HEAD, detail="not a PostgreSQL database"),
    ],
    ids=["current", "rollback", "unreachable-after-success", "sqlite"],
)
async def test_health_is_200_otherwise(health_client, status):
    async with health_client(status) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["schema"]["state"] == status.state


@pytest.mark.asyncio
async def test_sqlite_session_is_not_applicable_never_unverified(db_session):
    # The unit-test database is SQLite and has no version table. It must never
    # read as "behind" or as "unverified", or every test and every local dev run
    # touching /health would get 503.
    schema_check.reset_cache()
    status = await schema_check.current_status(db_session)
    schema_check.reset_cache()
    assert status.state == "not_applicable"
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


class _GoodSession(_PgSession):
    def __init__(self, rows=(("fo008",),)):
        self._rows = list(rows)

    async def execute(self, *_a, **_k):
        return self._rows


TRANSIENT = [TimeoutError(), ConnectionRefusedError(), OSError("dns")]


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", TRANSIENT)
async def test_unreachable_before_any_success_is_unverified_and_blocks(exc):
    # 2026-09-25 09:34:56: the first probe after a deploy hit a sleeping database,
    # read "unknown", and the deploy went live unchecked. A process that has never
    # completed a check must not take traffic on the strength of not knowing.
    schema_check.reset_cache()
    status = await schema_check.current_status(_PgSession(exc))
    schema_check.reset_cache()
    assert status.state == "unverified"
    assert status.blocks_traffic


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", TRANSIENT)
async def test_unreachable_after_a_success_is_unknown_and_does_not_block(exc, monkeypatch):
    # A running instance whose database naps must not be restarted for it.
    schema_check.reset_cache()
    assert (await schema_check.current_status(_GoodSession())).state == "current"
    monkeypatch.setattr(schema_check, "CACHE_SECONDS", 0.0)  # force a fresh probe
    status = await schema_check.current_status(_PgSession(exc))
    schema_check.reset_cache()
    assert status.state == "unknown"
    assert not status.blocks_traffic


@pytest.mark.asyncio
async def test_an_unverified_result_is_not_cached():
    # A deploy waiting on a waking database should go live on the first probe
    # that reaches it, not wait out CACHE_SECONDS behind a stale "unverified".
    schema_check.reset_cache()
    first = await schema_check.current_status(_PgSession(TimeoutError()))
    second = await schema_check.current_status(_GoodSession())
    schema_check.reset_cache()
    assert first.state == "unverified"
    assert second.state == "current"


@pytest.mark.asyncio
async def test_health_names_the_unverified_state(health_client):
    status = schema_check.SchemaStatus("unverified", HEAD, detail="TimeoutError")
    async with health_client(status) as c:
        r = await c.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "schema_unverified"


@pytest.mark.asyncio
async def test_health_names_the_misconfiguration(health_client):
    status = schema_check.SchemaStatus("misconfigured", HEAD, detail="InvalidPasswordError")
    async with health_client(status) as c:
        r = await c.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "database_misconfigured"


class _SlowSession(_PgSession):
    async def execute(self, *_a, **_k):
        import asyncio

        await asyncio.sleep(30)


@pytest.mark.asyncio
async def test_a_sleeping_database_answers_unknown_quickly(monkeypatch):
    # A probe on a database waking from idle must not hang past Render's own
    # health-check timeout: it answers within the bound. (In a fresh process that
    # answer is "unverified"; what this test pins is the time, not the state.)
    import time

    monkeypatch.setattr(schema_check, "DB_TIMEOUT_SECONDS", 0.2)
    schema_check.reset_cache()
    t0 = time.monotonic()
    status = await schema_check.current_status(_SlowSession(None))
    elapsed = time.monotonic() - t0
    schema_check.reset_cache()
    assert status.state == "unverified"
    assert elapsed < 2.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_connection_bounds_a_hung_connect():
    # The real driver, not a fake: a connect to an address that never answers
    # must give up inside Render's 5 s health-check limit. A fake that cancels
    # instantly can't tell a hard bound from a soft one (review of #249).
    import time

    from field_ops.config import settings
    from sqlalchemy.ext.asyncio import AsyncSession

    host = settings.db_url.split("@")[-1].split("/")[0]
    engine = schema_check.make_health_engine(settings.db_url.replace(host, "10.255.255.1:5433"))
    schema_check.reset_cache()
    t0 = time.monotonic()
    async with AsyncSession(engine) as s:
        status = await schema_check.current_status(s)
    elapsed = time.monotonic() - t0
    schema_check.reset_cache()
    await engine.dispose()
    assert status.state == "unverified"  # a fresh process that never reached its DB
    # Under 3 s, not merely under 5: the 4 s wait_for backstop would pass a
    # looser bound on its own, and this test exists to prove the DRIVER's bound.
    # Budget test below keeps the three-step worst case under the backstop.
    assert elapsed < 2.5, f"health probe took {elapsed:.1f}s; the driver connect bound is 1.5 s"


def test_worst_case_budget_fits_under_the_backstop_and_render():
    # connect + SELECT + rollback (the fresh-database path) must finish before the
    # wait_for backstop fires, and leave room under Render's 5 s for the response.
    # 2 commands: the SELECT and, on a fresh database, the rollback. The count
    # lives in database_revisions' docstring; change both together.
    worst = schema_check.HEALTH_CONNECT_TIMEOUT + 2 * schema_check.HEALTH_COMMAND_TIMEOUT
    assert worst < schema_check.DB_TIMEOUT_SECONDS, "backstop would fire on a correct probe"
    assert worst <= 3.0, "leave at least 2 s under Render's 5 s for TLS, FastAPI, response"


# --- production must be PostgreSQL, or the guard is inert ---------------------------
#
# Review of #256: not_applicable is the one state that passes without reading the
# database, and a sqlite DATABASE_URL isn't loopback, so it reads as production.
# Without a driver check that deploy boots and answers 200 with the guard inert.


def _prod_settings(database_url: str):
    from field_ops.config import Settings

    return Settings(
        _env_file=None,
        database_url=database_url,
        field_ops_jwt_secret="x" * 40,
        field_ops_storage_backend="r2",
        r2_account_id="a",
        r2_access_key_id="b",
        r2_secret_access_key="c",
        r2_bucket="d",
    )


def test_production_on_sqlite_refuses_to_start(monkeypatch):
    from field_ops.config import _assert_deployable

    monkeypatch.delenv("FIELD_OPS_DEV", raising=False)
    s = _prod_settings("sqlite+aiosqlite:///./field_ops.db")
    assert s.is_production, "the premise: a sqlite URL reads as production"
    with pytest.raises(RuntimeError, match="must be PostgreSQL"):
        _assert_deployable(s)


def test_production_on_postgres_passes_the_driver_check(monkeypatch):
    # The other direction: the same settings on a remote Postgres URL must boot,
    # or the check above is just a check that everything fails.
    from field_ops.config import _assert_deployable

    monkeypatch.delenv("FIELD_OPS_DEV", raising=False)
    s = _prod_settings("postgresql://u:p@db.example.neon.tech/pogf?sslmode=require")
    assert s.is_production
    _assert_deployable(s)  # must not raise
