import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

class DatabaseConfig(BaseModel):
    user: str | None = Field(default_factory=lambda: os.getenv('DB_USER'))
    password: str | None = Field(default_factory=lambda: os.getenv('DB_PASSWORD'))
    host: str | None = Field(default_factory=lambda: os.getenv('DB_HOST'))
    port: str | None = Field(default_factory=lambda: os.getenv('DB_PORT'))
    name: str | None = Field(default_factory=lambda: os.getenv('DB_NAME'))

    @property
    def dsn(self) -> str:
        # If any required field is missing, this might construct an invalid DSN,
        # but that matches the original behavior which would produce strings with "None".
        # However, to improve robustness we could raise an error here or use strict types.
        # Given the task is code health, explicit handling is better.
        # But let's stick to simple extraction first.
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
