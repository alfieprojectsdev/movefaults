"""
Async SQLAlchemy engine and session factory for the Field Ops service.

Uses asyncpg driver (postgresql+asyncpg://) for non-blocking DB access in
FastAPI's async request handlers.

Usage in routers:
    @router.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(User))
        ...
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from field_ops.config import settings

engine = create_async_engine(settings.db_url, echo=False, pool_pre_ping=True)

# expire_on_commit=False: prevents attributes from expiring after commit,
# which would trigger lazy loads (incompatible with async).
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a DB session and closes it after the request."""
    async with AsyncSessionLocal() as session:
        yield session
