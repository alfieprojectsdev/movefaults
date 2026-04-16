"""
Root conftest.py — monorepo sys.path setup for pytest.

Adds the repo root to sys.path so that `from src.db.models import ...` and
other root-relative imports resolve correctly when running tests from anywhere
in the monorepo tree.

The root `src/` directory is not registered as a hatch wheel source (only
service-specific src/ directories are), so pytest needs this explicit path
injection to resolve cross-service imports like `src.db.models`.
"""

import sys
from pathlib import Path

# Insert repo root so `from src.db.models import Base` resolves for any test
# that imports a module with a top-level cross-service dependency.
repo_root = Path(__file__).parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
