from src.config import DatabaseConfig
from src.database.writer import DatabaseWriter


def test_database_config_dsn():
    config = DatabaseConfig(
        user="test_user",
        password="test_password",
        host="test_host",
        port="5432",
        name="test_db"
    )
    assert config.dsn == "postgresql://test_user:test_password@test_host:5432/test_db"

def test_database_writer_uses_config():
    config = DatabaseConfig(
        user="writer_user",
        password="writer_password",
        host="writer_host",
        port="5432",
        name="writer_db"
    )
    writer = DatabaseWriter(config=config)
    assert writer.dsn == "postgresql://writer_user:writer_password@writer_host:5432/writer_db"

def test_database_writer_default_config(monkeypatch):
    monkeypatch.setenv("DB_USER", "env_user")
    monkeypatch.setenv("DB_PASSWORD", "env_password")
    monkeypatch.setenv("DB_HOST", "env_host")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "env_db")

    # Since we are instantiating a new DatabaseConfig inside DatabaseWriter (if None passed),
    # it should pick up these env vars.
    writer = DatabaseWriter()
    assert writer.dsn == "postgresql://env_user:env_password@env_host:5432/env_db"
