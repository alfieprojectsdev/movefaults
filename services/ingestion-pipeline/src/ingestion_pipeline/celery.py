from celery import Celery
import os

# Use environment variables for configuration, with defaults for local development
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6380") # Using the non-conflicting port

app = Celery(
    "ingestion_pipeline",
    broker=f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
    backend=f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
    include=["ingestion_pipeline.tasks"],
)

app.conf.update(
    result_expires=3600,
)

if __name__ == "__main__":
    app.start()
