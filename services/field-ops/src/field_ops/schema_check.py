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

# TIME BUDGET. Render counts a health check as passed only if it answers 2xx
# within 5 s (render.com/docs/health-checks, checked 2026-09-25). The hosted
# database sleeps when idle and can take seconds to wake, and asyncpg's default
# connect timeout is 60 s, so an unbounded probe could hang past Render's limit
# and get a healthy process restarted or a good deploy refused.
#
# The bound lives in the DRIVER, on a connection used only by /health:
#   connect           <= HEALTH_CONNECT_TIMEOUT  (a sleeping database is a slow connect)
#   each command      <= HEALTH_COMMAND_TIMEOUT
# The longest real path runs three steps: connect, the SELECT, and, when the
# version table doesn't exist yet (a fresh database, the first deploy, which is
# exactly the moment this guard exists for), a rollback. So the worst case is
# 1.5 + 0.75 + 0.75 = 3 s, leaving 2 s for TLS, FastAPI and the response. The
# connect is where the time actually goes; a one-row SELECT and a rollback don't
# need a second each once the connection is up.
#
# DB_TIMEOUT_SECONDS (asyncio.wait_for) is a BACKSTOP and cannot be a ceiling at
# any value. wait_for cancels and then awaits the driver's cleanup, and when a
# query is in flight asyncpg cleans up by opening a second TLS connection to send
# a cancel request, and that connection has no timeout at all (connect_utils
# _cancel takes none). So lowering this number makes an UNBOUNDED unwind more
# likely to be entered: it is the one knob here that gets worse when tightened.
# It must sit above the 3 s worst case, so the backstop never fires on a probe
# that was about to answer correctly. If probes are slow, tune the driver
# timeouts above, not this. (Both points raised in review of #249.)
#
# The app's own pool keeps the normal timeouts: a sub-second command limit there
# would break real requests while the database wakes.
#
# CACHE_SECONDS is part of this budget. Render stops traffic only after 15 s of
# CONSECUTIVE failures; with a 30 s cache, at most the first probe in each window
# can be slow, so a slow database can never string 15 s of failures together.
# Tuning the cache down removes that bound; don't, without re-checking this.
HEALTH_CONNECT_TIMEOUT = 1.5
HEALTH_COMMAND_TIMEOUT = 0.75
DB_TIMEOUT_SECONDS = 4.0  # backstop only, keep it above the 3 s worst case; see above

_health_engine = None


def make_health_engine(url: str):
    """The bounded engine /health uses. Separate so the bound can be tested for real."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from field_ops.config import settings

    return create_async_engine(
        url,
        poolclass=NullPool,  # one short connection per check, never a pooled one
        connect_args={
            **settings.db_connect_args,
            "timeout": HEALTH_CONNECT_TIMEOUT,
            "command_timeout": HEALTH_COMMAND_TIMEOUT,
        },
    )


def _get_health_engine():
    global _health_engine
    if _health_engine is None:
        from field_ops.config import settings

        _health_engine = make_health_engine(settings.db_url)
    return _health_engine


async def get_health_db():
    """FastAPI dependency: a session on the bounded health-check connection."""
    from sqlalchemy.ext.asyncio import AsyncSession as _S

    async with _S(_get_health_engine()) as session:
        yield session


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
