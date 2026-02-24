import importlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock celery before importing the module that uses it
sys.modules["celery"] = MagicMock()

class TestCeleryConfig(unittest.TestCase):
    def setUp(self):
        # Clear environment variables before each test
        self.env_patcher = patch.dict(os.environ, {}, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def test_redis_url_no_password(self):
        # Set environment variables
        os.environ["REDIS_HOST"] = "localhost"
        os.environ["REDIS_PORT"] = "6380"

        # Reload the module to pick up new env vars
        import ingestion_pipeline.celery as celery_mod
        importlib.reload(celery_mod)

        self.assertEqual(celery_mod.redis_url, "redis://localhost:6380/0")

    def test_redis_url_with_password(self):
        # Set environment variables
        os.environ["REDIS_HOST"] = "localhost"
        os.environ["REDIS_PORT"] = "6380"
        os.environ["REDIS_PASSWORD"] = "secret"

        # Reload the module to pick up new env vars
        import ingestion_pipeline.celery as celery_mod
        importlib.reload(celery_mod)

        self.assertEqual(celery_mod.redis_url, "redis://:secret@localhost:6380/0")

    def test_redis_url_with_special_chars_password(self):
        # Set environment variables
        os.environ["REDIS_HOST"] = "localhost"
        os.environ["REDIS_PORT"] = "6380"
        os.environ["REDIS_PASSWORD"] = "p@ss:word"

        # Reload the module to pick up new env vars
        import ingestion_pipeline.celery as celery_mod
        importlib.reload(celery_mod)

        self.assertEqual(celery_mod.redis_url, "redis://:p%40ss%3Aword@localhost:6380/0")

if __name__ == "__main__":
    unittest.main()
