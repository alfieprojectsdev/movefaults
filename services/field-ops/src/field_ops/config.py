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

    # JWT auth
    field_ops_jwt_secret: str = "change-me-in-production"
    field_ops_jwt_algorithm: str = "HS256"
    field_ops_jwt_expire_hours: int = 8  # long expiry suits field use (full day shift)

    # File storage (logsheet photos)
    field_ops_upload_dir: str = "/tmp/field-ops-uploads"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @computed_field  # type: ignore[misc]
    @property
    def db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.pogf_db_user}:{self.pogf_db_password}"
            f"@{self.pogf_db_host}:{self.pogf_db_port}/{self.pogf_db_name}"
        )


settings = Settings()
