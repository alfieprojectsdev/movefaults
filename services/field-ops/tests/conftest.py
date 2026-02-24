"""
Test fixtures for field-ops service tests.

Uses an in-memory SQLite database for fast, isolated unit tests.
Integration tests against a real PostgreSQL instance should be tagged
with @pytest.mark.integration and run separately.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from field_ops.main import app
from field_ops.models import FieldOpsBase
from field_ops.routers.auth import hash_password

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
