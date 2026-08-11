"""
Alembic migration environment for field-ops schema.

Uses asyncpg (postgresql+asyncpg://) to match the runtime driver — no
separate psycopg2 install needed.

Run from repo root:
    uv run alembic -c services/field-ops/alembic.ini upgrade head

This env.py is intentionally separate from the root migrations/env.py
— the field_ops schema has its own migration history and version tracking.
"""

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Make field_ops importable from the repo root
repo_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services/field-ops/src"))

from field_ops.dburl import connect_args_for, to_asyncpg_url  # noqa: E402
from field_ops.models import FieldOpsBase  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = FieldOpsBase.metadata


def get_url() -> str:
    """
    DATABASE_URL wins over the discrete POGF_DB_* fields, matching the runtime.

    DEPLOY.md documents exporting DATABASE_URL and then running both alembic
    trees. Before this precedence existed, that sequence migrated whatever
    POGF_DB_* pointed at — by default a local container — while the hosted
    database it was aimed at stayed empty. `alembic upgrade head` printed
    success either way, so the first failure was a 500 from the deployed API
    after the team had already been given the URL.
    """
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return to_asyncpg_url(explicit)

    return (
        "postgresql+asyncpg://"
        f"{os.getenv('POGF_DB_USER', 'pogf_user')}:"
        f"{os.getenv('POGF_DB_PASSWORD', 'pogf_password')}@"
        f"{os.getenv('POGF_DB_HOST', 'localhost')}:"
        f"{os.getenv('POGF_DB_PORT', '5433')}/"
        f"{os.getenv('POGF_DB_NAME', 'pogf_db')}"
    )


def do_run_migrations(connection):
    # The field_ops schema must exist before Alembic can write alembic_version into it.
    # Migration 001 also creates the schema, but Alembic checks for alembic_version first.
    connection.execute(
        __import__("sqlalchemy").text("CREATE SCHEMA IF NOT EXISTS field_ops")
    )
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema="field_ops",  # alembic_version lives in field_ops schema
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # connect_args carries the TLS requirement that get_url() had to strip for
    # asyncpg. Without it a hosted database is reached over opportunistic TLS
    # with no certificate verification — the migration would still succeed,
    # which is exactly why it would go unnoticed.
    engine = create_async_engine(
        get_url(),
        echo=False,
        connect_args=connect_args_for(os.getenv("DATABASE_URL", "")),
    )
    async with engine.begin() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="field_ops",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
