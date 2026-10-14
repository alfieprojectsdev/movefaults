"""Make `import epb` resolve when pytest runs from the repo root.

The spike's code is the `epb` package beside this file. It is deliberately not
installed into the workspace: it is research code, not a dependency of anything.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
