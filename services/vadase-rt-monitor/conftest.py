"""Make this service's own `src.` imports resolve when pytest runs from the
repo root.

Code inside vadase-rt-monitor imports as `from src.parsers.nmea_parser import
...` -- see the *Import Paths* section of the repo CLAUDE.md, where that
convention is deliberate and follows the hatch source mapping in
`pyproject.toml`. It resolves on its own only when the working directory is
this service, which is why `uv run pytest services/vadase-rt-monitor/tests/`
has always worked and a repo-root run has not.

`src` is a NAMESPACE package spanning two directories: `src/db/` at the repo
root, imported by the ingestion pipeline as `src.db.models`, and this
service's `src/`. Both portions have to stay namespace portions for that to
hold -- an `__init__.py` in either makes it a regular package, which wins the
path scan outright and hides the other. This service's `src/__init__.py` was
exactly that: an empty marker file that made `src.db` unimportable in any
process that had also put this directory on the path.
"""

import sys
from pathlib import Path

service_root = Path(__file__).parent
if str(service_root) not in sys.path:
    sys.path.insert(0, str(service_root))
