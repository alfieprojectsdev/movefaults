"""Write the API responses the frontend smoke test renders.

    uv run python services/bsw-console/tests/make_frontend_fixture.py

The responses come from the synthetic tree in conftest.py. Its one real file
is the LZY250360 protocol file that bernese-workflow's tests already commit, so
nothing new from a real campaign lands in the repo. Re-run it when a response
shape changes.
"""

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bsw_console.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from conftest import build  # noqa: E402

REPO = HERE.parents[2]
OUT = HERE.parent / "frontend" / "src" / "__fixtures__" / "api.json"
URLS = [
    "/api/session",
    "/api/lock",
    "/api/campaigns",
    "/api/campaigns/LUZON/years/2025/days",
    "/api/campaigns/LUZON/years/2025/runs",
    "/api/campaigns/LUZON/years/2025/days/35",
    "/api/campaigns/LUZON/years/2025/days/36/failure",
    "/api/campaigns/LUZON/years/2025/days/35/redo",
    "/api/campaigns/LUZON/years/2025/plan?start=35&end=40",
    "/api/known-errors",
    "/api/campaigns/LUZON/years/2025/station-files",
    "/api/campaigns/LUZON/years/2025/station-files/onsala-request",
    "/api/campaigns/LUZON/years/2025/station-files/apriori-preview",
    "/api/campaigns/LUZON/time-series",
    "/api/campaigns/LUZON/time-series/SYN1",
    "/api/equipment-report",
    "/api/stations/ALBU/equipment",
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = TestClient(create_app(build(Path(tmp))))
        data = {}
        for url in URLS:
            r = client.get(url)
            r.raise_for_status()
            data[url.split("?")[0]] = json.loads(
                r.text.replace(tmp, "/srv/bsw").replace(str(REPO), ".")
            )
        data["/api/plans"] = {"plans": []}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
