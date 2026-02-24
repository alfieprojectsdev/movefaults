import os
from urllib.parse import quote

from celery import Celery

# Use environment variables for configuration, with defaults for local development
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6380")  # Using the non-conflicting port
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")

# Construct Redis URL with authentication if password is provided
if REDIS_PASSWORD:
    # Use URL encoding for the password to handle special characters
    encoded_password = quote(REDIS_PASSWORD)
    redis_url = f"redis://:{encoded_password}@{REDIS_HOST}:{REDIS_PORT}/0"
else:
    redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

app = Celery(
    "ingestion_pipeline",
    broker=redis_url,
    backend=redis_url,
    include=["ingestion_pipeline.tasks"],
)

app.conf.update(
    result_expires=3600,
)

if __name__ == "__main__":
    app.start()
