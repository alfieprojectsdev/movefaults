"""
scripts/compare_solutions.sh must be able to say DIFFERS.

Two ways it could not, both found 2026-10-27 by the PHREF parity run:

* A plain (uncompressed) file went through `zcat ... 2>/dev/null`, which
  fails and prints nothing, so both sides were empty and compared equal.
  STA/FIN_*.CRD differing by up to 16 mm was reported "identical: 30".
* The strip pattern for run timestamps, `YY:DDD:SSSSS`, also matches the
  reference epoch on every SOLUTION/ESTIMATE line, so every coordinate was
  deleted before the diff: 10,983 of 11,331 lines of a real SINEX.

Each test below is a case the old script got wrong.
"""

from __future__ import annotations

import gzip
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "compare_solutions.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("gzip") is None,
    reason="needs bash and gzip",
)

SNX = """\
%=SNX 2.02 COD {created} COD 25:096:00000 25:096:86370 P 00003 2 S
+FILE/REFERENCE
 DESCRIPTION        PHIVOLCS daily solution
-FILE/REFERENCE
+INPUT/HISTORY
 +SNX 2.02 COD {created} COD 25:096:00000 25:096:86370 P 00003 2 S
-INPUT/HISTORY
*RNX2SNX_20251210: NEQ reduction and SINEX generation   {stamp}
+SOLUTION/ESTIMATE
*INDEX _TYPE_ CODE PT SOLN _REF_EPOCH__ UNIT S ___ESTIMATED_VALUE___ __STD_DEV__
     1 STAX   BRGC  A    1 25:096:43200 m    2 {x} 1.20000e-03
     2 STAY   BRGC  A    1 25:096:43200 m    2  1.23456789012345e+06 1.20000e-03
-SOLUTION/ESTIMATE
+SOLUTION/MATRIX_ESTIMATE L COVA
     1     1  1.44000000000000e-06
-SOLUTION/MATRIX_ESTIMATE
%ENDSNX
"""

CRD = """\
PHREF: final coordinates                                         {stamp}
--------------------------------------------------------------------------------
LOCAL GEODETIC DATUM: IGS20             EPOCH: 2025-04-06 12:00:00

NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG

  1  BRGC 22301M001  {x}   5492000.0000   1653000.0000    A
"""

X0 = " 3.12345678901234e+06"


def _snx(x: str = X0, created: str = "26:239:32400", stamp: str = "29-AUG-26 09:00") -> str:
    return SNX.format(x=x, created=created, stamp=stamp)


def _crd(x: str = "-3123456.7890", stamp: str = "29-AUG-26 09:00") -> str:
    return CRD.format(x=x, stamp=stamp)


def _write(d: Path, name: str, text: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    if name.endswith(".gz"):
        with gzip.open(d / name, "wt") as f:
            f.write(text)
    else:
        (d / name).write_text(text)


def _run(a: Path, b: Path, glob: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), str(a), str(b), glob], capture_output=True, text=True, timeout=60
    )


def test_run_timestamps_alone_are_identical(tmp_path: Path) -> None:
    """The control: two runs of the same inputs on different days must pass,
    or a red result below proves nothing."""
    _write(tmp_path / "A", "FIN_20250960.SNX.gz", _snx())
    _write(
        tmp_path / "B", "FIN_20250960.SNX.gz", _snx(created="26:300:61200", stamp="27-OCT-26 16:46")
    )
    r = _run(tmp_path / "A", tmp_path / "B", "FIN_*.SNX.gz")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "identical: 1" in r.stdout


def test_a_changed_coordinate_estimate_differs(tmp_path: Path) -> None:
    """4.4 mm in X, everything else equal, covariance included."""
    _write(tmp_path / "A", "FIN_20250960.SNX.gz", _snx())
    _write(tmp_path / "B", "FIN_20250960.SNX.gz", _snx(x=" 3.12345679341234e+06"))
    r = _run(tmp_path / "A", tmp_path / "B", "FIN_*.SNX.gz")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "differing: 1" in r.stdout
    assert "STAX   BRGC" in r.stdout, "the differing estimate line is shown"


def test_plain_files_are_compared_not_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "A", "FIN_20250960.CRD", _crd())
    _write(tmp_path / "B", "FIN_20250960.CRD", _crd(x="-3123456.7934", stamp="27-OCT-26 16:46"))
    r = _run(tmp_path / "A", tmp_path / "B", "FIN_*.CRD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "differing: 1" in r.stdout


def test_identical_plain_files_pass(tmp_path: Path) -> None:
    _write(tmp_path / "A", "FIN_20250960.CRD", _crd())
    _write(tmp_path / "B", "FIN_20250960.CRD", _crd(stamp="27-OCT-26 16:46"))
    r = _run(tmp_path / "A", tmp_path / "B", "FIN_*.CRD")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "identical: 1" in r.stdout


def test_an_unreadable_file_is_not_identical(tmp_path: Path) -> None:
    """A truncated .gz must not decompress to nothing on both sides and pass."""
    _write(tmp_path / "A", "FIN_20250960.SNX.gz", _snx())
    (tmp_path / "B").mkdir()
    (tmp_path / "B" / "FIN_20250960.SNX.gz").write_bytes(b"\x1f\x8b\x08\x00broken")
    r = _run(tmp_path / "A", tmp_path / "B", "FIN_*.SNX.gz")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "identical: 1" not in r.stdout


def test_two_empty_files_are_not_evidence(tmp_path: Path) -> None:
    _write(tmp_path / "A", "FIN_20250960.CRD", "")
    _write(tmp_path / "B", "FIN_20250960.CRD", "")
    r = _run(tmp_path / "A", tmp_path / "B", "FIN_*.CRD")
    assert r.returncode != 0, r.stdout + r.stderr
