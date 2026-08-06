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

    # Set to "1" on any internet-reachable deployment. Turns the weak-default
    # checks below from warnings into refusals — see _assert_deployable().
    field_ops_production: str = ""

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
    def is_production(self) -> bool:
        return self.field_ops_production == "1"


_WEAK_JWT_SECRET = "change-me-in-production"


def _assert_deployable(s: Settings) -> None:
    """
    Refuse to start a production instance with development defaults.

    This fails CLOSED and runs before the app serves anything. The JWT secret is
    the one that matters most: with the shipped default, anyone who reads this
    open-source repo can mint a valid token for a public URL and post logsheets
    as any user. A service that boots happily in that state is worse than one
    that will not boot, because nobody finds out.
    """
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

    if not s.database_url:
        problems.append("DATABASE_URL is unset")

    if problems:
        # Names and conditions only — never the values.
        raise RuntimeError(
            "Refusing to start in production mode:\n  - " + "\n  - ".join(problems)
        )


settings = Settings()
_assert_deployable(settings)
