"""
Synchronous SQLAlchemy session factory for ingestion-pipeline Celery workers.

Celery tasks run in dedicated worker processes (not an async event loop), so
we use plain create_engine / sessionmaker here — not the async variants used
by the FastAPI field-ops service.

Both services connect to the same PostgreSQL instance; the sync vs async
choice is purely about execution context, not database compatibility.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# The central POGF PostgreSQL database.
# Defaults to the docker-compose port (5433) for local development.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5433/pogf_db",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
