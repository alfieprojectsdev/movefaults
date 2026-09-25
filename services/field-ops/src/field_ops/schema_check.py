"""
Does the database schema match the code that is about to serve it?

WHY THIS EXISTS
On 2026-09-23 the field PWA returned 500 on every screen touching
`station_proposals`. fo008 had been merged two days earlier and never applied:
Render deployed the new code from `main`, and nothing ran the migration. The
automation meant to run it (field_ops_migrate.yml) could not start, first
because Actions was disabled and then because the account was billing-locked.
See SETTLED.md §4 and §6.

A guard that depends on some other system running is only as good as that
system. This one lives in the service itself. `/health` is Render's health
check (render.yaml: healthCheckPath), and Render only switches traffic to a new
deploy once it passes. So when this module reports the database BEHIND the
code, `/health` answers 503, the deploy fails, and the previous version keeps
serving. The failure surfaces in the Render dashboard at deploy time instead of
as a 500 in an observer's hand.

WHAT COUNTS AS A FAILURE, AND WHAT DELIBERATELY DOES NOT
- behind: every revision the database records is known to this code, and
  it is not the code's head (or the version table is missing or empty).
  -> 503. This is the outage case.
- current: the database is at the code's head. -> 200.
- unrecognised: the database records a revision this code has never heard of.
  That is what a rollback looks like: the migration ran, then an older deploy
  came back. Old code on an additively-migrated schema normally works, and
  failing health here would block the rollback that is being used to recover.
  -> 200, and it is reported so it can be seen.
- misconfigured: the database refused this deploy's own settings (wrong or
  expired password, missing database, missing rights). -> 503. These do not go
  away on retry, and serving with them is the 23 Sep outage by another door:
  every route that touches the database fails while /health says ok.
- unknown: the database could not be asked (unreachable, timed out, or not
  PostgreSQL, as in the SQLite unit tests). -> 200.
  This includes failures that ARE permanent but arrive as connection errors: a
  suspended or billing-disabled database endpoint looks exactly like one waking
  from idle at probe time. They are treated as transient because they cannot be
  told apart in the moment, not because they were overlooked. Such a deploy
  takes traffic and fails on every database route; the guard does not cover it. A health check that fails on
  a transient database blip makes Render restart a healthy process, and the
  hosted database can take seconds to wake from idle.

The expected head comes from the migration files shipped in the image. If they
are missing, `expected_heads()` raises, and the app refuses to start: a build
that forgot to copy them fails its deploy rather than passing every check.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

# In the repo: services/field-ops/src/field_ops/schema_check.py -> services/field-ops/migrations
# In the image: /app/src/field_ops/schema_check.py            -> /app/migrations
_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

CACHE_SECONDS = 30.0

# The revision query must answer well inside Render's health-check timeout. The
# hosted database sleeps when idle and can take seconds to wake; without a bound,
# a probe landing on a sleeping database hangs until Render gives up on the probe
# itself, and a healthy process gets restarted or a good deploy refused. A query
# that doesn't answer in time reads as "unknown" (200), like any other
# transient failure.
DB_TIMEOUT_SECONDS = 3.0


def migrations_dir() -> Path:
    return Path(os.environ.get("FIELD_OPS_MIGRATIONS_DIR") or _DEFAULT_MIGRATIONS_DIR)


@lru_cache(maxsize=1)
def _script_directory(path: str):
    from alembic.script import ScriptDirectory

    if not (Path(path) / "versions").is_dir():
        raise RuntimeError(
            f"field-ops migrations not found at {path}. The image must ship "
            "services/field-ops/migrations (see the Dockerfile), or set "
            "FIELD_OPS_MIGRATIONS_DIR. Refusing to start without knowing the "
            "expected schema revision."
        )
    return ScriptDirectory(path)


def expected_heads() -> frozenset[str]:
    """The head revision(s) of the migration files this code ships with."""
    script = _script_directory(str(migrations_dir()))
    heads = frozenset(script.get_heads())
    if not heads:
        raise RuntimeError(f"no migration heads found under {migrations_dir()}")
    return heads


def known_revisions() -> frozenset[str]:
    script = _script_directory(str(migrations_dir()))
    return frozenset(rev.revision for rev in script.walk_revisions())


@dataclass(frozen=True)
class SchemaStatus:
    state: str  # "current" | "behind" | "misconfigured" | "unrecognised" | "unknown"
    expected: frozenset[str] = field(default_factory=frozenset)
    database: frozenset[str] = field(default_factory=frozenset)
    detail: str = ""

    @property
    def blocks_traffic(self) -> bool:
        return self.state in ("behind", "misconfigured")

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "expected": sorted(self.expected),
            "database": sorted(self.database),
            **({"detail": self.detail} if self.detail else {}),
        }


def classify(
    expected: frozenset[str], known: frozenset[str], database: frozenset[str]
) -> SchemaStatus:
    """Pure decision, kept separate so every case is testable without a database."""
    if database == expected:
        return SchemaStatus("current", expected, database)
    if not database:
        return SchemaStatus(
            "behind", expected, database, "no revision recorded: migrations never applied"
        )
    if database <= known:
        return SchemaStatus(
            "behind",
            expected,
            database,
            "database is at an older revision than this code; run "
            "`alembic -c services/field-ops/alembic.ini upgrade head` against the "
            "hosted database, then redeploy",
        )
    return SchemaStatus(
        "unrecognised",
        expected,
        database,
        "database records a revision this code does not ship; usually a rollback "
        "after a migration, which is safe for additive migrations",
    )


async def database_revisions(session: AsyncSession) -> frozenset[str] | None:
    """Revisions recorded in field_ops.alembic_version; None when not determinable."""
    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        return None
    try:
        rows = await session.execute(text("SELECT version_num FROM field_ops.alembic_version"))
    except ProgrammingError:
        # The table does not exist: nothing was ever migrated. That is "behind".
        await session.rollback()
        return frozenset()
    return frozenset(r[0] for r in rows)


# Errors that will not go away on the next probe, because they come from this
# deploy's own settings: a wrong or expired password, a database name that does
# not exist, a role without rights. Failing closed on these costs nothing: the
# previous deploy keeps serving, and it has working settings by construction.
# Failing closed on a TRANSIENT error would cost a restart loop, so those stay
# "unknown". Matched by name so the check does not import the driver, and
# looked up along the exception chain because SQLAlchemy may wrap them.
PERMANENT_ERRORS = frozenset(
    {
        "InvalidPasswordError",
        "InvalidAuthorizationSpecificationError",
        "InvalidCatalogNameError",
        "InsufficientPrivilegeError",
    }
)


def permanent_error_name(exc: BaseException) -> str | None:
    seen: set[int] = set()
    todo: list[BaseException | None] = [exc]
    while todo:
        e = todo.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        if type(e).__name__ in PERMANENT_ERRORS:
            return type(e).__name__
        todo += [getattr(e, "orig", None), e.__cause__, e.__context__]
    return None


_cache: tuple[float, SchemaStatus] | None = None


async def current_status(session: AsyncSession) -> SchemaStatus:
    """Schema status, re-checked at most every CACHE_SECONDS."""
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    expected = expected_heads()
    try:
        database = await asyncio.wait_for(database_revisions(session), DB_TIMEOUT_SECONDS)
    except Exception as exc:
        permanent = permanent_error_name(exc)
        if permanent:
            status = SchemaStatus(
                "misconfigured",
                expected,
                detail=f"database rejected this deploy's settings: {permanent}",
            )
        else:  # timed out, refused, DNS, waking from idle: may pass on the next probe
            status = SchemaStatus(
                "unknown", expected, detail=f"database not reachable: {type(exc).__name__}"
            )
    else:
        if database is None:
            status = SchemaStatus("unknown", expected, detail="not a PostgreSQL database")
        else:
            status = classify(expected, known_revisions(), database)
    _cache = (now, status)
    return status


def reset_cache() -> None:
    global _cache
    _cache = None
