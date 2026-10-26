"""Run ledger: what run_days records, and the status read back from it.

The status cases are the point of step D: a slow day, a dead driver and a
halted run must give different answers, which a count of FIN files cannot.
"""

from __future__ import annotations

import gzip
import json
import socket
from pathlib import Path

import pytest
from bernese_workflow.backends import BPEResult
from bernese_workflow.ledger import Ledger, config_hash, main, read_entries, run_status
from bernese_workflow.month_driver import run_days

HELMR1_PRT = Path(__file__).parent / "fixtures" / "bpe_errors" / "LZY250360_RP250360_513_000.PRT"
HOST = socket.gethostname()


class Backend:
    """Writes the FIN on success; leaves the HELMR1 PRT in BPE/ on failure."""

    def __init__(self, sol: Path, fail=(), kill=None):
        self.sol, self.fail, self.kill = sol, set(fail), kill

    def run(self, campaign: str, year: int, session: str) -> BPEResult:
        doy = int(session[:3])
        if doy == self.kill:
            raise KeyboardInterrupt
        if doy in self.fail:
            (self.sol / "BPE" / f"RP{year % 100:02d}{session}_513_000.PRT").write_bytes(
                HELMR1_PRT.read_bytes()
            )
            return BPEResult(False, None, None, False, False)
        with gzip.open(self.sol / f"FIN_{year}{session}.NQ0.gz", "wb") as f:
            f.write(b"x")
        return BPEResult(True, None, None, False, False)


@pytest.fixture
def sol(tmp_path: Path) -> Path:
    (tmp_path / "BPE").mkdir()
    return tmp_path


def _events(path: Path) -> list[str]:
    return [e["event"] for e in read_entries(path)[0]]


def test_config_hash_follows_content_not_order(tmp_path: Path):
    a, b = tmp_path / "A.PCF", tmp_path / "B.INP"
    a.write_text("one")
    b.write_text("two")
    h = config_hash([a, b])
    assert h == config_hash([b, a]) and len(h) == 12
    b.write_text("three")
    assert config_hash([a, b]) != h


def test_every_attempt_is_recorded(sol: Path):
    (sol / "FIN_20250010.NQ0.gz").write_bytes(gzip.compress(b"x"))
    (sol / "FIN_20250010.done").touch()
    led = Ledger(sol / "ledger.jsonl")
    run_days(
        Backend(sol, fail={3}),
        "LUZON",
        2025,
        [1, 2, 3],
        sol_dir=sol,
        bpe_dir=sol / "BPE",
        ledger=led,
        config="abc123",
        station_counts={2: 34, 3: 41},
    )
    entries, bad = read_entries(sol / "ledger.jsonl")
    assert bad == 0
    assert [e["event"] for e in entries] == [
        "run_start",
        "attempt_start",
        "attempt_end",
        "attempt_start",
        "attempt_end",
        "run_end",
    ]
    start, end = entries[0], entries[-1]
    assert start["banked"] == [1] and start["doys"] == [1, 2, 3] and start["config"] == "abc123"
    assert {e["run"] for e in entries} == {start["run"]}
    ok, failed = entries[2], entries[4]
    assert (ok["doy"], ok["outcome"], ok["stations"]) == (2, "ok", 34)
    assert (failed["doy"], failed["outcome"], failed["stations"]) == (3, "failed", 41)
    assert failed["error"].startswith("HELMR1")
    assert end["halt"] is None


def test_no_ledger_writes_nothing(sol: Path):
    run_days(Backend(sol), "LUZON", 2025, [1], sol_dir=sol, bpe_dir=sol / "BPE")
    assert not list(sol.glob("*.jsonl"))


def test_a_torn_last_line_is_skipped_and_counted(tmp_path: Path):
    led = Ledger(tmp_path / "l.jsonl")
    led.run_start(campaign="X", year=2025, doys=[1], banked=[])
    with open(tmp_path / "l.jsonl", "a") as f:
        f.write('{"v":1,"event":"attempt_st')
    entries, bad = read_entries(tmp_path / "l.jsonl")
    assert len(entries) == 1 and bad == 1


def test_finished_run(sol: Path):
    led = Ledger(sol / "l.jsonl")
    run_days(Backend(sol), "LUZON", 2025, [1, 2], sol_dir=sol, bpe_dir=sol / "BPE", ledger=led)
    st = run_status(read_entries(sol / "l.jsonl")[0])
    assert (st.state, st.exit_code) == ("finished", 1)


def test_halted_run_is_broken_and_says_why(sol: Path):
    led = Ledger(sol / "l.jsonl")
    run_days(
        Backend(sol, fail={1, 2, 3}),
        "LUZON",
        2025,
        [1, 2, 3, 4],
        sol_dir=sol,
        bpe_dir=sol / "BPE",
        ledger=led,
    )
    st = run_status(read_entries(sol / "l.jsonl")[0])
    assert (st.state, st.exit_code) == ("halted", 4)
    text = "\n".join(st.lines)
    assert "HALTED" in text and "failed DOY 003: HELMR1" in text
    assert "not yet attempted 1" in text


def test_killed_driver_is_dead_not_slow(sol: Path):
    led = Ledger(sol / "l.jsonl")
    with pytest.raises(KeyboardInterrupt):
        run_days(
            Backend(sol, kill=2),
            "LUZON",
            2025,
            [1, 2, 3],
            sol_dir=sol,
            bpe_dir=sol / "BPE",
            ledger=led,
        )
    entries = read_entries(sol / "l.jsonl")[0]
    # A SIGKILL runs no handler, so it leaves no run_end: drop the one that the
    # interrupt wrote to get what a killed driver leaves behind.
    killed = [e for e in entries if e["event"] != "run_end"]
    st = run_status(killed, alive=lambda host, pid: False)
    assert (st.state, st.exit_code) == ("dead", 3)
    assert "during DOY 002" in "\n".join(st.lines)


def test_an_interrupted_run_says_so_rather_than_looking_dead(sol: Path):
    """Ctrl-C, or the SIGTERM a service stop becomes, is a deliberate stop. It
    must close the run, or status reports it running until the pid goes and
    dead after."""
    led = Ledger(sol / "l.jsonl")
    with pytest.raises(KeyboardInterrupt):
        run_days(
            Backend(sol, kill=2),
            "LUZON",
            2025,
            [1, 2, 3],
            sol_dir=sol,
            bpe_dir=sol / "BPE",
            ledger=led,
        )
    entries = read_entries(sol / "l.jsonl")[0]
    ends = [e for e in entries if e["event"] == "run_end"]
    assert len(ends) == 1 and ends[0]["halt"] == "interrupted: KeyboardInterrupt"
    st = run_status(entries, alive=lambda host, pid: False)
    assert (st.state, st.exit_code) == ("halted", 4)


def _synthetic(now: float, *, typical_s: float, current_s: float) -> list[dict]:
    """A live run: three ok days of typical_s, then one in progress for current_s."""
    e = [
        {
            "event": "run_start",
            "run": "r1",
            "ts": now - 9999,
            "host": HOST,
            "pid": 1,
            "doys": [1, 2, 3, 4],
            "banked": [],
        }
    ]
    for d in (1, 2, 3):
        e.append(
            {
                "event": "attempt_end",
                "run": "r1",
                "ts": now - 9000 + d,
                "doy": d,
                "outcome": "ok",
                "seconds": typical_s,
            }
        )
    e.append({"event": "attempt_start", "run": "r1", "ts": now - current_s, "doy": 4})
    return e


def test_days_run_in_parallel_are_compared_with_parallel_runs():
    """A block of days in flight is judged against earlier blocks, not against
    single days, or every block looks slow."""
    now = 1_000_000.0
    e = [
        {
            "event": "run_start",
            "run": "r1",
            "ts": now - 99999,
            "host": HOST,
            "pid": 1,
            "doys": list(range(1, 11)),
            "banked": [],
        }
    ]
    for d in range(1, 6):  # five single days of 300 s
        e.append(
            {
                "event": "attempt_end",
                "run": "r1",
                "ts": now - 90000 + d,
                "doy": d,
                "outcome": "ok",
                "seconds": 300,
            }
        )
    for d in (6, 7):  # two days that ran in a block that took 1800 s
        e.append(
            {
                "event": "attempt_end",
                "run": "r1",
                "ts": now - 80000 + d,
                "doy": d,
                "outcome": "ok",
                "seconds": 1800,
                "mode": "block",
            }
        )
    for d in (8, 9, 10):  # a block in flight for 2000 s
        e.append(
            {"event": "attempt_start", "run": "r1", "ts": now - 2000, "doy": d, "mode": "block"}
        )
    st = run_status(e, now=now, alive=lambda h, p: True)
    text = "\n".join(st.lines)
    assert (st.state, st.exit_code) == ("running", 0), text
    assert "3 days in progress (DOY 008-010)" in text


def test_config_hash_tells_option_directories_apart(tmp_path: Path):
    """R2S_GEN/ADDNEQ2.INP and R2S_FIN/ADDNEQ2.INP share a name."""
    gen, fin = tmp_path / "R2S_GEN", tmp_path / "R2S_FIN"
    gen.mkdir()
    fin.mkdir()
    (gen / "ADDNEQ2.INP").write_text("MAXPAR 6000")
    h = config_hash([gen / "ADDNEQ2.INP"])
    (gen / "ADDNEQ2.INP").rename(fin / "ADDNEQ2.INP")
    assert config_hash([fin / "ADDNEQ2.INP"]) != h


def test_slow_day_is_slow_not_dead():
    now = 1_000_000.0
    st = run_status(_synthetic(now, typical_s=300, current_s=900), now=now, alive=lambda h, p: True)
    assert (st.state, st.exit_code) == ("slow", 2)
    st = run_status(_synthetic(now, typical_s=300, current_s=400), now=now, alive=lambda h, p: True)
    assert (st.state, st.exit_code) == ("running", 0)


def test_run_on_another_host_is_not_called_running():
    now = 1_000_000.0
    st = run_status(_synthetic(now, typical_s=300, current_s=100), now=now, alive=lambda h, p: None)
    assert st.state == "unknown"


def test_status_reads_the_latest_run_only(sol: Path):
    led = Ledger(sol / "l.jsonl")
    run_days(
        Backend(sol, fail={1, 2, 3}),
        "LUZON",
        2025,
        [1, 2, 3],
        sol_dir=sol,
        bpe_dir=sol / "BPE",
        ledger=led,
    )
    run_days(
        Backend(sol),
        "LUZON",
        2025,
        [1, 2, 3],
        sol_dir=sol,
        bpe_dir=sol / "BPE",
        ledger=Ledger(sol / "l.jsonl"),
    )
    st = run_status(read_entries(sol / "l.jsonl")[0])
    assert st.state == "finished"


def test_cli_exit_code_carries_the_state(sol: Path, capsys):
    assert main(["status", str(sol / "missing.jsonl")]) == 5
    led = Ledger(sol / "l.jsonl")
    run_days(Backend(sol), "LUZON", 2025, [1], sol_dir=sol, bpe_dir=sol / "BPE", ledger=led)
    assert main(["status", str(sol / "l.jsonl")]) == 1
    assert capsys.readouterr().out.startswith("NONE")


def test_entries_are_one_json_object_per_line(sol: Path):
    led = Ledger(sol / "l.jsonl")
    run_days(Backend(sol), "LUZON", 2025, [1], sol_dir=sol, bpe_dir=sol / "BPE", ledger=led)
    for line in (sol / "l.jsonl").read_text().splitlines():
        assert isinstance(json.loads(line), dict)


def test_extra_fields_pass_through_and_not_run_counts_as_ended(tmp_path: Path):
    """Step F tags parallel attempts (mode, block) and closes days it never
    started as not_run; neither may leave a day looking in progress."""
    led = Ledger(tmp_path / "l.jsonl")
    led.run_start(campaign="PHREF", year=2025, doys=[1, 2, 3], banked=[])
    for d in (1, 2, 3):
        led.attempt_start(doy=d, session=f"{d:03d}0", mode="block", block=[1, 3])
    led.attempt_end(doy=1, session="0010", outcome="ok", seconds=900.0, mode="block", block=[1, 3])
    led.attempt_end(doy=2, session="0020", outcome="failed", seconds=900.0, mode="block")
    led.attempt_end(
        doy=3,
        session="0030",
        outcome="not_run",
        seconds=0.0,
        mode="block",
        note="not started: queue stopped at DOY 002",
    )
    entries = read_entries(tmp_path / "l.jsonl")[0]
    starts = [e for e in entries if e["event"] == "attempt_start"]
    assert starts[0]["mode"] == "block" and starts[0]["block"] == [1, 3]
    st = run_status(entries, alive=lambda h, p: True)
    text = "\n".join(st.lines)
    assert "in progress" not in text, text
    assert "ok 1   failed 1   not run 1   not yet attempted 0" in text, text
