"""
Pydantic settings for the Field Ops API service.

All values are read from environment variables first, then fall back to the
defaults below (which match docker-compose.yml so local dev requires no config).

Set FIELD_OPS_JWT_SECRET to a real random value in production:
    python -c "import secrets; print(secrets.token_hex(32))"
"""

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database — same PostgreSQL instance as central POGF DB
    pogf_db_user: str = "pogf_user"
    pogf_db_password: str = "pogf_password"
    pogf_db_host: str = "localhost"
    pogf_db_port: int = 5433
    pogf_db_name: str = "pogf_db"

    # Public origins allowed to call the API cross-origin, comma-separated.
    # Not needed when the PWA is served behind a same-origin rewrite.
    field_ops_cors_origins: str = ""

    # JWT auth
    field_ops_jwt_secret: str = "change-me-in-production"
    field_ops_jwt_algorithm: str = "HS256"
    field_ops_jwt_expire_hours: int = 8  # long expiry suits field use (full day shift)

    # File storage (logsheet photos)
    # "local" writes to disk — development only. A container filesystem is
    # ephemeral, so a deployed instance MUST use "r2" or the photo rows will
    # point at files that no longer exist.
    field_ops_storage_backend: str = "local"
    field_ops_upload_dir: str = "/tmp/field-ops-uploads"

    # Cloudflare R2 — required when field_ops_storage_backend == "r2".
    # Values come from the environment; never commit them.
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""

    # Full connection string, which is how hosted Postgres (Neon, Supabase,
    # Railway) hands it over. Takes precedence over the discrete fields above.
    database_url: str = ""

    # Set to "1" to declare a deployment explicitly. Note this is no longer the
    # only way to be in production — a remote DATABASE_URL infers it. See
    # is_production() and _assert_deployable().
    field_ops_production: str = ""

    # The one escape hatch: run locally against a remote database without the
    # deployment checks. Deliberately not the default, and announced when used.
    field_ops_dev: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @computed_field  # type: ignore[misc]
    @property
    def db_url(self) -> str:
        if self.database_url:
            # Neon and most providers hand out a `postgresql://` (or `postgres://`)
            # URL, but SQLAlchemy needs the async driver named explicitly or it
            # loads psycopg2 and fails at import.
            url = self.database_url
            for prefix in ("postgresql+asyncpg://", "postgres://", "postgresql://"):
                if url.startswith(prefix):
                    if prefix != "postgresql+asyncpg://":
                        url = "postgresql+asyncpg://" + url[len(prefix):]
                    break
            # asyncpg rejects libpq's ?sslmode= parameter; it negotiates TLS via
            # its own `ssl` argument. Neon's copy-paste string includes it, and
            # leaving it in produces a confusing connect error at first request.
            #
            # Stripping it is necessary, but stripping it ALONE would silently
            # drop the requirement the operator asked for: asyncpg's default is
            # opportunistic TLS with no certificate verification, so the DB
            # password and every logsheet would cross the public internet with
            # no MITM protection. db_connect_args below translates the
            # requirement instead of discarding it.
            if "?" in url:
                base, _, query = url.partition("?")
                kept = [
                    kv for kv in query.split("&")
                    if kv and not kv.startswith(("sslmode=", "channel_binding="))
                ]
                url = base + ("?" + "&".join(kept) if kept else "")
            return url

        return (
            f"postgresql+asyncpg://{self.pogf_db_user}:{self.pogf_db_password}"
            f"@{self.pogf_db_host}:{self.pogf_db_port}/{self.pogf_db_name}"
        )

    @property
    def db_connect_args(self) -> dict:
        """
        asyncpg connect args, carrying the TLS requirement db_url had to strip.

        libpq's `sslmode=require` cannot be passed to asyncpg, so db_url removes
        it. Removing it without translation would leave asyncpg on its default
        (`ssl=None`) — opportunistic TLS with **no certificate verification** —
        which is strictly weaker than what the connection string asked for.

        A verifying SSLContext is returned whenever the source URL requested TLS
        or the database is not on this machine. `ssl.create_default_context()`
        verifies the chain and the hostname, which is what `sslmode=verify-full`
        means and what a managed provider over the public internet requires.

        Keyed on remoteness rather than on is_production deliberately: a
        FIELD_OPS_DEV=1 run against Neon still crosses the public internet, and
        the password should not.

        Note this is deliberately NOT applied to the discrete-field local dev
        path, where the database is a container on localhost with no certificate.
        """
        import ssl as _ssl

        source = self.database_url or ""
        wants_tls = (
            "sslmode=" in source
            and "sslmode=disable" not in source
        ) or (bool(source) and not _is_loopback(source))

        if not wants_tls:
            return {}
        return {"ssl": _ssl.create_default_context()}

    @property
    def is_dev_override(self) -> bool:
        return self.field_ops_dev == "1"

    @property
    def is_production(self) -> bool:
        """
        True when this process should be held to deployment standards.

        Inferred, not declared. Requiring FIELD_OPS_PRODUCTION=1 made the whole
        fail-closed gate opt-in: forgetting one environment variable on the
        hosting platform silently restored every weak default the gate exists to
        catch — including the JWT secret that is published in this repository.
        A safety check that has to be switched on is not a safety check.

        The signal that a process is deployed is that it talks to a database
        somewhere else. Nobody points local development at Neon by accident, and
        in the rare case where it is deliberate, FIELD_OPS_DEV=1 says so out loud.
        The discrete pogf_db_* path (a container on localhost) is untouched, so
        `docker compose up` and pytest need no new configuration.
        """
        if self.is_dev_override:
            return False
        if self.field_ops_production == "1":
            return True
        return bool(self.database_url) and not _is_loopback(self.database_url)


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "db", "postgres", "host.docker.internal"}


def _is_loopback(database_url: str) -> bool:
    """
    True when the URL points at a database on this machine or compose network.

    Parsed rather than substring-matched: `postgres://u:p@ep-x.neon.tech/localhost`
    contains "localhost" and is emphatically not local. urlsplit().hostname also
    strips credentials and the port and lowercases the host for us.
    """
    from urllib.parse import urlsplit

    try:
        host = urlsplit(database_url).hostname
    except ValueError:
        # Unparseable — treat as remote. Failing towards the strict checks is
        # the right direction for a malformed connection string.
        return False
    return host is not None and host in _LOOPBACK_HOSTS


_WEAK_JWT_SECRET = "change-me-in-production"


def _assert_deployable(s: Settings) -> None:
    """
    Refuse to start a production instance with development defaults.

    This fails CLOSED and runs before the app serves anything. The JWT secret is
    the one that matters most: with the shipped default, anyone who reads this
    open-source repo can mint a valid token for a public URL and post logsheets
    as any user. A service that boots happily in that state is worse than one
    that will not boot, because nobody finds out.

    See Settings.is_production for how "production" is decided — it is inferred
    from a remote DATABASE_URL, not declared by an environment variable that can
    be forgotten.
    """
    if s.is_dev_override and s.database_url and not _is_loopback(s.database_url):
        # Say it plainly. This is a remote database being treated as scratch, and
        # a stray FIELD_OPS_DEV=1 in a deployment environment would disable every
        # check below — so it must never be silent.
        import warnings

        warnings.warn(
            "FIELD_OPS_DEV=1: deployment checks SKIPPED against a non-local "
            "DATABASE_URL. Weak defaults (JWT secret, local photo storage) are "
            "in effect. Never set this on a deployed instance.",
            RuntimeWarning,
            stacklevel=2,
        )

    if not s.is_production:
        return

    problems: list[str] = []

    if s.field_ops_jwt_secret == _WEAK_JWT_SECRET or len(s.field_ops_jwt_secret) < 32:
        problems.append(
            "FIELD_OPS_JWT_SECRET is unset, default, or under 32 chars "
            "(generate: python -c \"import secrets; print(secrets.token_hex(32))\")"
        )

    if s.field_ops_storage_backend.lower() != "r2":
        problems.append(
            "FIELD_OPS_STORAGE_BACKEND must be 'r2' in production — a container "
            "filesystem is ephemeral, so photos written to disk are lost on restart"
        )
    else:
        # Checked HERE, not at first upload. get_storage() is only reached from
        # the photo endpoint, so validating there means a deploy with a typo'd
        # R2_BUCKET boots healthy, passes its health check, accepts logsheets,
        # and 500s on every photo forever — with nobody finding out until a
        # field team comes back. Names only; never the values.
        missing_r2 = [
            name
            for name, value in (
                ("R2_ACCOUNT_ID", s.r2_account_id),
                ("R2_ACCESS_KEY_ID", s.r2_access_key_id),
                ("R2_SECRET_ACCESS_KEY", s.r2_secret_access_key),
                ("R2_BUCKET", s.r2_bucket),
            )
            if not value
        ]
        if missing_r2:
            problems.append(
                "FIELD_OPS_STORAGE_BACKEND=r2 but these are unset: "
                + ", ".join(missing_r2)
            )

    if not s.database_url:
        problems.append("DATABASE_URL is unset")

    if problems:
        # Names and conditions only — never the values.
        raise RuntimeError(
            "Refusing to start in production mode:\n  - " + "\n  - ".join(problems)
        )


settings = Settings()
_assert_deployable(settings)
