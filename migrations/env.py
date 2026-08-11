"""
Alembic environment for the POGF centralized geodetic database.

DB URL is constructed from environment variables (with defaults matching
the docker-compose.yml configuration):

  POGF_DB_USER     default: pogf_user
  POGF_DB_PASSWORD default: pogf_password
  POGF_DB_HOST     default: localhost
  POGF_DB_PORT     default: 5433
  POGF_DB_NAME     default: pogf_db

Usage:
  docker compose up -d
  uv run alembic upgrade head          # apply all migrations
  uv run alembic downgrade -1          # roll back one migration
  uv run alembic revision --autogenerate -m "describe change"
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Make 'src.db.models' importable when alembic is run from the repo root
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.models import Base  # noqa: E402

# ---------------------------------------------------------------------------
# Alembic Config object (gives access to values in alembic.ini)
# ---------------------------------------------------------------------------
config = context.config

# Set up Python logging from alembic.ini config section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the DB URL with environment variables so we never hard-code
# credentials in a committed file.
#
# DATABASE_URL takes precedence over the discrete POGF_DB_* fields, matching
# how the services resolve their own connection (see field_ops.config.db_url).
# Without that precedence, DEPLOY.md's documented sequence — export DATABASE_URL,
# then run both alembic trees — quietly migrated whatever POGF_DB_* pointed at,
# defaulting to a local container. The hosted database stayed empty, `alembic
# upgrade head` reported success, and the first request to the deployed API was
# the thing that finally failed.
_explicit_url = os.getenv("DATABASE_URL", "").strip()
if _explicit_url:
    # This tree runs under a synchronous driver, so an async URL cannot be used
    # verbatim, and libpq understands ?sslmode= — unlike asyncpg, nothing needs
    # stripping here.
    db_url = _explicit_url.replace("postgresql+asyncpg://", "postgresql://", 1)
else:
    db_url = (
        "postgresql://"
        f"{os.getenv('POGF_DB_USER', 'pogf_user')}:"
        f"{os.getenv('POGF_DB_PASSWORD', 'pogf_password')}@"
        f"{os.getenv('POGF_DB_HOST', 'localhost')}:"
        f"{os.getenv('POGF_DB_PORT', '5433')}/"
        f"{os.getenv('POGF_DB_NAME', 'pogf_db')}"
    )
config.set_main_option("sqlalchemy.url", db_url)

# The metadata object Alembic uses for --autogenerate comparison
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — generate SQL without a live DB connection.

    Useful for reviewing migration SQL before applying it:
      uv run alembic upgrade head --sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode against a live database connection.
    Uses a single connection (no connection pooling) for migration safety.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
