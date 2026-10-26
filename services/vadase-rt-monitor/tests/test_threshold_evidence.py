"""scripts/threshold_evidence.py: the helpers behind the published threshold figures.

The real captures are not in the repository, so these use synthetic $GNLVM
lines. Each test pins one behaviour the review of #269 found missing.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from functools import reduce
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "threshold_evidence.py"


@pytest.fixture(scope="module")
def te():
    spec = importlib.util.spec_from_file_location("threshold_evidence", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["threshold_evidence"] = mod  # @dataclass looks the module up here
    spec.loader.exec_module(mod)
    return mod


T0 = datetime(2025, 10, 10, 1, 0, 0, tzinfo=UTC)


def lvm(t: datetime, v_east_mm_s: float) -> str:
    """A valid $GNLVM line: east velocity only, cq 20 mm/s."""
    body = (
        f"GNLVM,{t:%H%M%S}.00,{t:%m%d%y},{v_east_mm_s / 1000:.5f},0.0,0.0,"
        "0.0,0.0,0.0,0.0,0.0,0.0,0.020,12"
    )
    cs = reduce(lambda a, c: a ^ ord(c), body, 0)
    return f"${body}*{cs:02X}"


def test_truncated_line_is_rejected_not_fatal(te, tmp_path: Path):
    good = lvm(T0, 3.0)
    (tmp_path / "a.rtl").write_text(
        "\n".join([good, good[:-2], good[:-3] + "00", good.split("*")[0][:30] + "*"])
    )
    rows, rejected = te.load(tmp_path, "*.rtl")
    assert len(rows) == 1 and rejected == 3


def test_exactly_the_threshold_does_not_cross(te):
    """check_event_threshold alarms on >, so 15.00 is not a crossing."""
    assert not te.crosses(15.0)
    assert te.crosses(15.01)
    rows = [(T0 + timedelta(seconds=i), h, 20.0) for i, h in enumerate([15.0, 16.0, 17.0, 15.0])]
    assert te.longest_run(rows) == 2


def test_a_gap_ends_a_run(te):
    rows = [
        (T0, 20.0, 0.0),
        (T0 + timedelta(seconds=1), 20.0, 0.0),
        (T0 + timedelta(seconds=12), 20.0, 0.0),
    ]
    assert te.longest_run(rows) == 2


def test_overlapping_event_windows_explain_a_reading_once(te, tmp_path: Path, monkeypatch, capsys):
    """Two events 2 min apart: a crossing inside both windows is explained once."""
    (tmp_path / "x").mkdir()
    lines = [lvm(T0 + timedelta(seconds=i), 30.0 if i in (180, 181) else 2.0) for i in range(600)]
    (tmp_path / "x" / "a.rtl").write_text("\n".join(lines))
    t = T0.replace(tzinfo=None)
    cap = te.Capture(
        "swarm",
        "x/*.rtl",
        6.7,
        125.3,
        "test",
        [
            te.Event(f"{t:%Y-%m-%dT%H:%M:%S}", "5", 6.5, 123.7, 10.0),
            te.Event(f"{t + timedelta(minutes=2):%Y-%m-%dT%H:%M:%S}", "5", 6.5, 123.7, 10.0),
        ],
    )
    monkeypatch.setattr(te, "CAPTURES", [cap])
    monkeypatch.setattr(sys, "argv", ["threshold_evidence.py", "--data", str(tmp_path)])
    te.main()
    out = capsys.readouterr().out
    assert "readings > 15: 2" in out
    assert "not within 10 min of a listed event: 0" in out
