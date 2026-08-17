"""
Connection-string handling, shared by the app and the migration environment.

Kept out of ``config.py`` deliberately. Importing that module instantiates
``Settings`` and runs the fail-closed deployment gate as a side effect, which is
right for a process about to serve traffic and wrong for ``alembic upgrade``:
an operator migrating a hosted database from a laptop has no reason to have a
production JWT secret or R2 credentials to hand, and refusing to run migrations
over their absence would be a check firing at the wrong moment.

So the parts both need — translating a provider URL for asyncpg, and deciding
whether a host is local — live here, where importing them costs nothing.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Hosts that mean "this machine or this compose network". Anything else is
# treated as remote, which is what drives both the TLS requirement and the
# production inference in config.py.
LOOPBACK_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "[::1]", "db", "postgres", "host.docker.internal"}
)

# asyncpg negotiates TLS through its own `ssl` argument and rejects libpq's
# query parameters outright.
_ASYNCPG_UNSUPPORTED_PARAMS = ("sslmode=", "channel_binding=")


def is_loopback(database_url: str) -> bool:
    """
    True when the URL points at a database on this machine or compose network.

    Parsed rather than substring-matched: ``postgres://u:p@ep-x.neon.tech/localhost``
    contains "localhost" and is emphatically not local. ``urlsplit().hostname``
    also strips credentials and the port and lowercases the host.

    An unparseable URL counts as remote — failing towards the strict checks is
    the right direction for a malformed connection string.
    """
    try:
        host = urlsplit(database_url).hostname
    except ValueError:
        return False
    return host is not None and host in LOOPBACK_HOSTS


def to_asyncpg_url(raw: str) -> str:
    """
    Rewrite a provider connection string for SQLAlchemy's asyncpg driver.

    Neon and most hosted providers hand out ``postgresql://`` (or the older
    ``postgres://``). SQLAlchemy needs the async driver named explicitly, or it
    loads psycopg2 and fails at import.

    ``?sslmode=`` is stripped because asyncpg rejects it — but stripping it is
    only half the job, and the dangerous half on its own: asyncpg's default is
    opportunistic TLS with no certificate verification, so a URL that asked for
    ``sslmode=require`` would silently end up weaker than requested. See
    ``connect_args_for``, which carries the requirement across.
    """
    url = raw
    for prefix in ("postgresql+asyncpg://", "postgres://", "postgresql://"):
        if url.startswith(prefix):
            if prefix != "postgresql+asyncpg://":
                url = "postgresql+asyncpg://" + url[len(prefix):]
            break

    if "?" in url:
        base, _, query = url.partition("?")
        kept = [
            kv
            for kv in query.split("&")
            if kv and not kv.startswith(_ASYNCPG_UNSUPPORTED_PARAMS)
        ]
        url = base + ("?" + "&".join(kept) if kept else "")

    return url


def connect_args_for(raw: str) -> dict:
    """
    asyncpg connect args carrying the TLS requirement ``to_asyncpg_url`` stripped.

    A verifying ``SSLContext`` is returned whenever the source URL requested TLS
    or the database is not on this machine. ``ssl.create_default_context()``
    verifies the chain and the hostname — what ``sslmode=verify-full`` means, and
    what a managed provider reached over the public internet requires.

    Keyed on remoteness rather than on a production flag: a deliberate local run
    against a hosted database still crosses the public internet, and the password
    should not.
    """
    import ssl as _ssl

    if not raw:
        return {}

    wants_tls = (
        "sslmode=" in raw and "sslmode=disable" not in raw
    ) or not is_loopback(raw)

    return {"ssl": _ssl.create_default_context()} if wants_tls else {}
