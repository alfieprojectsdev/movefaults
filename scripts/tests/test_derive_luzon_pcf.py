"""
scripts/derive_luzon_pcf.py: the frame it writes, and which PCF it won't replace.

--frame defaults to i20, production's. i14 can't run on 5.4 at this epoch, so it
must not be able to replace the live LUZON_DLY.PCF by being the only flag given.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "derive_luzon_pcf.py"

STOCK = """\
V_PCV    = I20;  DESCRIPTION=x
V_REFINF = IGS20;  DESCRIPTION=x
V_REFPSD = IGS20;  DESCRIPTION=x
V_SATSYS = GRE;  DESCRIPTION=x
"""


def _run(u: Path, *args: str) -> subprocess.CompletedProcess[str]:
    (u / "PCF").mkdir(exist_ok=True)
    (u / "PCF" / "RNX2SNX.PCF").write_text(STOCK)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env={**os.environ, "U": str(u)},
        capture_output=True,
        text=True,
    )


def test_default_frame_is_production(tmp_path: Path) -> None:
    r = _run(tmp_path, "--apply")
    assert r.returncode == 0, r.stderr
    written = (tmp_path / "PCF" / "LUZON_DLY.PCF").read_text()
    assert "V_PCV    = I20;" in written
    assert "V_REFINF = IGS20;" in written
    assert "V_REFPSD = IGS20;" in written
    assert "V_SATSYS = GPS;" in written


def test_i14_refuses_to_replace_the_live_pcf(tmp_path: Path) -> None:
    (tmp_path / "PCF").mkdir()
    live = tmp_path / "PCF" / "LUZON_DLY.PCF"
    live.write_text("the live PCF\n")
    r = _run(tmp_path, "--frame", "i14", "--apply")
    assert r.returncode == 1
    assert "REFUSING" in r.stderr
    assert live.read_text() == "the live PCF\n"


def test_i14_writes_to_another_dest(tmp_path: Path) -> None:
    dest = tmp_path / "other.PCF"
    r = _run(tmp_path, "--frame", "i14", "--apply", "--dest", str(dest))
    assert r.returncode == 0, r.stderr
    written = dest.read_text()
    assert "V_PCV    = I14;" in written
    assert "V_REFINF = IGS14;" in written
    assert "V_REFPSD = IGS14;" in written
