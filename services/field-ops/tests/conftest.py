"""
Test fixtures for field-ops service tests.

Uses an in-memory SQLite database for fast, isolated unit tests.
Integration tests against a real PostgreSQL instance should be tagged
with @pytest.mark.integration and run separately.
"""

import os

import pytest_asyncio
from field_ops.main import app
from field_ops.models import FieldOpsBase
from field_ops.routers.auth import hash_password
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# SQLite async URL — no server needed for unit tests.
# Note: SQLite doesn't support PostgreSQL-specific features (UUID native, JSONB),
# so tests verify routing and business logic, not DB-level constraints.
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_engine():
    # schema_translate_map strips "field_ops." prefix so SQLite (which has no
    # schema namespacing) can create the tables without error.
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        execution_options={"schema_translate_map": {"field_ops": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(FieldOpsBase.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        sync_session_class=None,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    from field_ops.database import get_db
    from field_ops.models import User

    # Seed a test user
    user = User(
        username="testuser",
        hashed_password=hash_password("testpass"),
        role="field_staff",
    )
    db_session.add(user)
    await db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client):
    """Return Authorization headers for an authenticated test user."""
    resp = await client.post(
        "/api/v1/token",
        data={"username": "testuser", "password": "testpass"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def pytest_configure(config):
    """Register the `integration` marker this conftest's docstring anticipates.

    It was described here from the start and never registered, so any test
    using it emitted `PytestUnknownMarkWarning`. FO-001 is the first ticket
    with tests that genuinely cannot run on SQLite, so it is the first to need
    the marker to mean something.

    Registered here rather than in the root `pyproject.toml` because the repo
    has no `[tool.pytest.ini_options]` section at all; adding one would change
    config discovery for every package to fix a warning in this one.
    """
    config.addinivalue_line(
        "markers",
        "integration: needs a real PostgreSQL/PostGIS instance; skipped without one.",
    )


# ---------------------------------------------------------------------------
# Postgres integration fixture — the prerequisite FO-001's design named
# ---------------------------------------------------------------------------
#
# The unit fixtures above run on in-memory SQLite, which cannot exercise:
#   * `public.stations` — not in FieldOpsBase.metadata, so create_all skips it
#   * ST_Y / ST_X / ST_MakePoint — no PostGIS
#   * partial unique indexes — the duplicate guard's third layer
#
# That is why `GET /api/v1/stations` had zero coverage before this ticket: an
# inability, not an oversight.
#
# This fixture points at the docker-compose TimescaleDB on 5433, which bundles
# PostGIS. It SKIPS rather than fails when the database is absent, so the suite
# stays green on a laptop with nothing running — a fixture that turns the whole
# suite red when Docker is down would just get deleted.

FIELD_OPS_TEST_PG_URL = os.environ.get(
    "FIELD_OPS_TEST_DATABASE_URL",
    "postgresql+asyncpg://pogf:pogf@localhost:5433/pogf",
)


@pytest_asyncio.fixture
async def pg_engine():
    """A live Postgres engine, or skip.

    Deliberately does NOT create or drop schemas. Pointing a destructive
    fixture at a URL that might be someone's real database is how test
    infrastructure eats production data; tests using this are responsible for
    their own rows and should clean up after themselves.
    """
    import pytest

    engine = create_async_engine(FIELD_OPS_TEST_PG_URL, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa_text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any connection failure means skip
        await engine.dispose()
        pytest.skip(f"no PostgreSQL at {FIELD_OPS_TEST_PG_URL}: {type(exc).__name__}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    session_factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
