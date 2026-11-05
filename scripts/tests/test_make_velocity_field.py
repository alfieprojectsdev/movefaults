"""make_velocity_field.py says when a station is far from its reference.

East, North and Up are the reference's axes, so a far-away reference rotates a
station's motion between them. Once a field is a map that cannot be seen, so the
files themselves must say it. The station is still mapped: the method stays.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pogf_geodetic_suite.timeseries.gmt import reference_distances

SCRIPT = Path(__file__).resolve().parents[1] / "make_velocity_field.py"
REF = (-3186000.0, 5345000.0, 1640000.0)


def _crd(path: Path, rows: dict[str, tuple[float, float, float]]) -> Path:
    head = (
        "SYNTHETIC\n" + "-" * 40 + "\nLOCAL GEODETIC DATUM: IGS20\n\n"
        " NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG     SYSTEM\n\n"
    )
    lines = [
        f"{i:3d}  {name} 00000S000  {x:>15.5f} {y:>15.5f}  {z:>15.5f}    A   G"
        for i, (name, (x, y, z)) in enumerate(rows.items(), start=1)
    ]
    path.write_text(head + "\n".join(lines) + "\n", encoding="ascii")
    return path


def _run(tmp_path: Path, rows: dict, ref: str = "REF0") -> tuple[subprocess.CompletedProcess, Path]:
    data = tmp_path / "data"
    data.mkdir()
    sites = [s for s in rows if s != ref]
    (data / "123").write_text("\n".join(sites) + "\n")
    for site in sites:
        epochs = [2020 + k / 12 for k in range(36)]
        (data / site).write_text(
            "".join(f"{t:.4f} {0.01 * (t - 2020):.5f} {0.02 * (t - 2020):.5f} 0.0\n" for t in epochs)
        )
    crd = _crd(tmp_path / "F1_20001.CRD", rows)
    out = tmp_path / "field"
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--data", str(data), "--crd", str(crd), "--ref", ref,
         "--out", str(out), "--offsets", str(tmp_path / "no-offsets")],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    return done, out


ROWS = {
    "REF0": REF,
    "NEAR": (REF[0], REF[1] + 100_000.0, REF[2]),  # 0.9 degrees
    "AWAY": (REF[0], REF[1] + 1_000_000.0, REF[2]),  # 9.0 degrees
}


def _text(out: Path, ext: str) -> str:
    return out.with_name(out.name + ext).read_text(encoding="utf-8")


def test_a_far_station_is_named_in_both_headers_and_the_log_and_is_still_mapped(tmp_path) -> None:
    done, out = _run(tmp_path, ROWS)
    for ext in (".psvelo", ".vert"):
        text = _text(out, ext)
        header = [x for x in text.splitlines() if x.startswith("#")]
        (note,) = [x for x in header if "over 5 degrees from REF0" in x]
        assert "1 of 2 stations (AWAY)" in note and "rotated" in note, ext
        rows = [x for x in text.splitlines() if not x.startswith("#")]
        assert any("AWAY" in r for r in rows), f"{ext}: warned about, not withheld"
        assert any("NEAR" in r for r in rows), ext
    log = _text(out, ".log")
    assert "AWAY: NOTE — 9.0 degrees from reference REF0" in log
    assert "NEAR: NOTE" not in log
    assert "over 5 degrees from REF0" in done.stdout


def test_nothing_far_says_so_quietly(tmp_path) -> None:
    done, out = _run(tmp_path, {k: v for k, v in ROWS.items() if k != "AWAY"})
    assert "over 5 degrees from REF0: 0 of 1 stations\n" in _text(out, ".psvelo")
    assert "rotated" not in _text(out, ".psvelo") and "NOTE" not in done.stdout


def test_a_reference_not_in_the_crd_says_it_could_not_check(tmp_path) -> None:
    done, out = _run(tmp_path, ROWS, ref="GONE")
    assert "reference distance not checked: GONE is not an estimated station" in _text(out, ".psvelo")
    assert "not checked" in done.stdout
    assert "not checked" in _text(out, ".log"), "the log is read alone; silence would read as a pass"


def test_a_long_reference_name_is_the_four_character_code_the_crd_is_keyed_on(tmp_path) -> None:
    crd = _crd(tmp_path / "F1_20001.CRD", ROWS)
    distances = reference_distances(crd, "ref000phl")
    assert distances is not None and set(distances) == {"NEAR", "AWAY"}
