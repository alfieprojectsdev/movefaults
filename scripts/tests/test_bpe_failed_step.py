"""
scripts/bpe_failed_step.sh: which BPE step failed in this attempt.

run_luzon_month.sh used to take the last `NNN_NNN <word>` match in the BPE
summary (LUZON_DLY.OUT) as the failed step. On a real summary that match is a
row of the job table at the bottom (`322_007      0`), so every failed day was
reported "at 0". The step is named in the failed step's own PRT, so that is
where the helper looks. The PRTs here are real ones, copied from the
bernese-workflow fixtures and renamed the way the month driver names them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "bpe_failed_step.sh"
FIXTURES = (
    Path(__file__).resolve().parents[2] / "services/bernese-workflow/tests/fixtures/bpe_errors"
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def run(bpe: Path, tag: str, since: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), str(bpe), tag, str(int(since))],
        capture_output=True,
        text=True,
        check=False,
    )


def place(bpe: Path, fixture: str, name: str, mtime: float) -> Path:
    dst = bpe / name
    shutil.copyfile(FIXTURES / fixture, dst)
    os.utime(dst, (mtime, mtime))
    return dst


def test_names_the_failed_step_and_its_error(tmp_path: Path) -> None:
    now = time.time()
    place(tmp_path, "LZY250360_RP250360_513_000.PRT", "RS251220_513_000.PRT", now)
    r = run(tmp_path, "251220", now - 60)
    assert r.returncode == 0
    assert r.stdout.startswith("PID 513 HELMCHK")
    assert "NO REDUNDANCY" in r.stdout
    assert "RS251220_513_000.PRT" in r.stdout


def test_a_prt_from_before_this_attempt_is_not_the_failure(tmp_path: Path) -> None:
    """A failure left from an earlier run must not be reported as today's."""
    now = time.time()
    place(tmp_path, "LZY250360_RP250360_513_000.PRT", "RS251220_513_000.PRT", now - 3600)
    r = run(tmp_path, "251220", now - 60)
    assert r.returncode == 1
    assert r.stdout == ""


def test_another_sessions_failure_is_ignored(tmp_path: Path) -> None:
    now = time.time()
    place(tmp_path, "LZY250360_RP250360_513_000.PRT", "RS251230_513_000.PRT", now)
    assert run(tmp_path, "251220", now - 60).returncode == 1


def test_only_the_last_attempt_in_an_appended_prt_counts(tmp_path: Path) -> None:
    """RUNBPE appends each attempt to the PRT (writePrtFileHeader opens `>>`).
    An earlier attempt's ERR must not make a step that then succeeded look failed."""
    now = time.time()
    prt = place(tmp_path, "LZY250360_RP250360_513_000.PRT", "RS251220_513_000.PRT", now)
    with prt.open("a") as f:
        f.write(
            "\n PROTOCOL FILE FOR BPE SCRIPT\n ----------------------------\n"
            " Script name        : HELMCHK\n"
            " 27-OCT-2026  10:18:30  00:00:01            MSG HELMR1    PROGRAM ENDED\n"
        )
    os.utime(prt, (now, now))
    assert run(tmp_path, "251220", now - 60).returncode == 1


def test_the_newest_failure_wins(tmp_path: Path) -> None:
    now = time.time()
    place(tmp_path, "LUZON_RP251210_022_002.PRT", "RS251220_022_002.PRT", now - 30)
    place(tmp_path, "LZY250360_RP250360_513_000.PRT", "RS251220_513_000.PRT", now)
    r = run(tmp_path, "251220", now - 60)
    assert r.stdout.startswith("PID 513 HELMCHK"), r.stdout


def test_a_step_that_ran_cleanly_is_not_reported(tmp_path: Path) -> None:
    now = time.time()
    ok = tmp_path / "RS251220_511_000.PRT"
    ok.write_text(
        " PROTOCOL FILE FOR BPE SCRIPT\n Script name        : ADDNEQ2\n"
        " 27-OCT-2026  10:17:00  00:00:01            MSG ADDNEQ2   PROGRAM ENDED\n"
    )
    os.utime(ok, (now, now))
    assert run(tmp_path, "251220", now - 60).returncode == 1


def test_the_error_text_under_the_header_is_shown(tmp_path: Path) -> None:
    """CCRNXO's header names the routine; what went wrong is on the indented line
    under it ("No input files"). Showing only the header names no problem."""
    now = time.time()
    place(tmp_path, "LUZON_RP251210_022_002.PRT", "RS251210_022_002.PRT", now)
    r = run(tmp_path, "251210", now - 60)
    assert "O_CCRNXO:concatenateOrMergeRinexFiles" in r.stdout
    assert "No input files" in r.stdout


def test_a_warning_after_the_error_does_not_replace_it(tmp_path: Path) -> None:
    """### is a warning. One printed after the *** error must not be shown as the cause."""
    now = time.time()
    prt = tmp_path / "RS251220_513_000.PRT"
    text = (FIXTURES / "LZY250360_RP250360_513_000.PRT").read_text()
    err_at = text.index(" *** PGM HELMR1")
    text = text[:err_at] + text[err_at:].replace(
        "\n\n", "\n\n ### PG HELMR1: SOME LATER WARNING\n\n", 1
    )
    prt.write_text(text)
    os.utime(prt, (now, now))
    r = run(tmp_path, "251220", now - 60)
    assert "NO REDUNDANCY" in r.stdout
    assert "LATER WARNING" not in r.stdout


# ---------------------------------------------------------------------------
# run_luzon_month.sh end to end, against a fake Bernese environment
# ---------------------------------------------------------------------------

MONTH = Path(__file__).resolve().parents[1] / "run_luzon_month.sh"

# The bottom of a failed BPE summary: a job table whose rows end in a count.
# This is the shape that made the old lookup print "at 0".
FAILED_OUT = """\
 Sessions finished: OK: 0  Error: 1

 PID_SUB  Script    Status
 513_000  HELMCHK   ERROR
 322_007        0
"""

FAKE_DRIVER = r"""#!/usr/bin/perl
# Stand-in for $U/SCRIPT/luzon_pcs.pl: one failed session, as BSW leaves it.
use File::Copy;
my $bpe = "$ENV{P}/LUZON/BPE";
open(my $o, '>', "$bpe/LUZON_DLY.OUT") or die;
print $o $ENV{FAKE_OUT};
close($o);
copy($ENV{FAKE_PRT}, "$bpe/RS251220_513_000.PRT") or die;
exit 1;
"""


def _fake_bernese(home: Path) -> dict[str, str]:
    P, U, S = home / "P", home / "U", home / "S"
    (P / "LUZON" / "BPE").mkdir(parents=True)
    (U / "PCF").mkdir(parents=True)
    (U / "SCRIPT").mkdir(parents=True)
    (S / "LUZON" / "2025" / "SOL").mkdir(parents=True)
    (U / "PCF" / "LUZON_DLY.PCF").write_text("V_PCV = I20;\n")
    driver = U / "SCRIPT" / "luzon_pcs.pl"
    driver.write_text(FAKE_DRIVER)
    driver.chmod(0o755)
    (home / "BERN54").mkdir()
    (home / "BERN54" / "LOADGPS.setvar").write_text(f"export P={P}\nexport U={U}\nexport S={S}\n")
    env = {k: v for k, v in os.environ.items() if k not in ("P", "U", "S")}
    env.update(
        HOME=str(home),
        LUZON_DOY_FROM="122",
        LUZON_DOY_TO="122",
        LUZON_SKIP_DOYS="",
        FAKE_OUT=FAILED_OUT,
        FAKE_PRT=str(FIXTURES / "LZY250360_RP250360_513_000.PRT"),
    )
    return env


def _month_run(script: Path, home: Path) -> str:
    env = _fake_bernese(home)
    r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 1, r.stdout + r.stderr  # one failed day
    return (home / "luzon-month-logs" / "summary.txt").read_text()


@pytest.mark.skipif(shutil.which("perl") is None, reason="needs perl")
def test_a_failed_day_names_its_step_not_a_job_table_count(tmp_path: Path) -> None:
    summary = _month_run(MONTH, tmp_path)
    fail = next(line for line in summary.splitlines() if "DOY 122  start" in line)
    assert "at PID 513 HELMCHK" in fail, fail
    assert "NO REDUNDANCY" in fail
    assert " at 0 " not in fail
