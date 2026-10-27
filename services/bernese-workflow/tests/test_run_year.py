"""Tests for run_year: blocks of parallel sessions, each in a private campaign.

The fake backend behaves the way BSW's server does with SUPERBPE=1, RADIO_P=1,
REPR_MODE=1 and NEXTSESS=0 (MENU/bpe.cpp, startSessions): sessions start in
order, at most MAXSESS at a time, and after the first error no new session is
started while the ones already running finish. Failed sessions leave their
private campaign with the step's real PRT from the fixtures; successful ones
leave a FIN in SOL and their campaign, which run_year must delete only after
banking the day.
"""

from __future__ import annotations

import gzip
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from bernese_workflow.backends import SessionsResult, repr_campaign_name
from bernese_workflow.run_year import SimplePlan, chunks, run_year

FIXTURES = Path(__file__).parent / "fixtures" / "bpe_errors"
YEAR = 2025

# A failed session's step output: (fixture stem, PID_SUB it is filed under).
FAILURES = {
    "helmr1": ("LZY250360_RP250360_513_000", "513_000"),  # session scope: counted
    "maxpar": ("MXPREP_MX230100_511_000", "511_000"),  # configuration: stops at once
}


@dataclass
class FakeBSW:
    campaign_dir: Path
    sol_dir: Path
    outcomes: dict[int, str] = field(default_factory=dict)  # doy -> ok | helmr1 | maxpar
    calls: list[tuple[int, int, int]] = field(default_factory=list)
    raise_on: int | None = None  # first doy of a call that raises (a timeout)

    def run_sessions(self, campaign, year, first_session, n_sessions, *, maxsess, repr_prefix):
        first = int(first_session[:3])
        self.calls.append((first, n_sessions, maxsess))
        statuses: dict[str, str] = {}
        stop_at: int | None = None
        for i, doy in enumerate(range(first, first + n_sessions)):
            if stop_at is not None and i >= stop_at + maxsess:
                break  # queued behind the error: never started
            session = f"{doy:03d}0"
            tag = f"{year % 100:02d}{session}"
            camp = self.campaign_dir / repr_campaign_name(repr_prefix, year, session)
            (camp / "BPE").mkdir(parents=True)
            kind = self.outcomes.get(doy, "ok")
            if kind == "ok":
                fin = self.sol_dir / f"FIN_{year}{session}.NQ0.gz"
                with gzip.open(fin, "wb") as f:
                    f.write(b"NEQ " * 64)
                statuses[tag] = "finished"
            else:
                stem, pid_sub = FAILURES[kind]
                dst = camp / "BPE" / f"RP{tag}_{pid_sub}"
                shutil.copyfile(FIXTURES / f"{stem}.PRT", dst.with_suffix(".PRT"))
                shutil.copyfile(FIXTURES / f"{stem}.LOG", dst.with_suffix(".LOG"))
                statuses[tag] = "error"
                if stop_at is None:
                    stop_at = i
        if self.raise_on == first:
            raise RuntimeError("BPE timed out after 7200s")
        return SessionsResult(success=stop_at is None, raw_log="", statuses=statuses)


@pytest.fixture
def env(tmp_path: Path):
    camp = tmp_path / "P"
    sol = tmp_path / "S" / "PHREF" / str(YEAR) / "SOL"
    (camp / "PHREF" / "BPE").mkdir(parents=True)
    sol.mkdir(parents=True)
    return camp, sol


def go(bsw: FakeBSW, plan: SimplePlan, **kw):
    kw.setdefault("maxsess", 3)
    kw.setdefault("preflight", False)
    return run_year(
        bsw,
        plan,
        campaign="PHREF",
        repr_prefix="PHR",
        campaign_dir=bsw.campaign_dir,
        sol_dir=bsw.sol_dir,
        **kw,
    )


def by_doy(out):
    return {o.doy: o.status for o in out}


def test_a_clean_block_is_one_call_and_every_day_is_banked(env) -> None:
    camp, sol = env
    bsw = FakeBSW(camp, sol)
    out = go(bsw, SimplePlan(YEAR, list(range(152, 158))))
    assert bsw.calls == [(152, 6, 3)]
    assert by_doy(out) == dict.fromkeys(range(152, 158), "ok")
    for d in range(152, 158):
        assert (sol / f"FIN_{YEAR}{d:03d}0.done").exists()


def test_a_successful_days_campaign_is_deleted_only_after_it_is_banked(env) -> None:
    camp, sol = env
    out = go(FakeBSW(camp, sol), SimplePlan(YEAR, [152, 153]))
    assert by_doy(out) == {152: "ok", 153: "ok"}
    assert not (camp / "PHR251520").exists()
    assert not (camp / "PHR251530").exists()
    assert (camp / "PHREF").is_dir(), "the base campaign is never touched"


def test_a_session_error_resumes_after_the_failed_day_and_keeps_its_campaign(env) -> None:
    """NEXTSESS=0 stops the queue at the first error; run_year restarts from the
    day after it, the way run_phref_year.sh's resume loop does."""
    camp, sol = env
    bsw = FakeBSW(camp, sol, outcomes={153: "helmr1"})
    out = go(bsw, SimplePlan(YEAR, list(range(152, 160))), maxsess=2, chunk_days=8)
    st = by_doy(out)
    assert st[153] == "failed"
    assert all(st[d] == "ok" for d in (152, 154, 155, 156, 157, 158, 159))
    assert bsw.calls[0] == (152, 8, 2)
    assert bsw.calls[1][0] > 153, "the failed day is not retried in the same run"
    assert (camp / "PHR251530" / "BPE").is_dir(), "a failed campaign is kept for autopsy"
    failed = next(o for o in out if o.doy == 153)
    assert "HELMR1" in failed.error


def test_a_configuration_error_stops_the_run_at_once(env) -> None:
    camp, sol = env
    bsw = FakeBSW(camp, sol, outcomes={154: "maxpar"})
    out = go(bsw, SimplePlan(YEAR, list(range(152, 162))), maxsess=2)
    st = by_doy(out)
    assert st[154] == "failed"
    assert len(bsw.calls) == 1, "no second block after a configuration error"
    assert all(s in ("ok", "failed", "not_run") for s in st.values())
    assert {d for d, s in st.items() if s == "not_run"} >= set(range(157, 162))
    assert "neqckdim" in next(o for o in out if o.doy == 154).error


def test_days_finished_in_parallel_beside_a_failure_are_banked(env) -> None:
    """With MAXSESS=3 the two sessions already running when 152 fails still
    finish; their days must be banked, not re-run."""
    camp, sol = env
    bsw = FakeBSW(camp, sol, outcomes={152: "helmr1"})
    out = go(bsw, SimplePlan(YEAR, list(range(152, 158))), maxsess=3)
    st = by_doy(out)
    assert st[152] == "failed" and st[153] == "ok" and st[154] == "ok"
    resumed = bsw.calls[1:]
    assert resumed and resumed[0][0] == 155, "the resume starts at the first day not yet run"


def test_banked_days_are_not_run_again(env) -> None:
    camp, sol = env
    go(FakeBSW(camp, sol), SimplePlan(YEAR, [152, 153, 154]))
    again = FakeBSW(camp, sol)
    out = go(again, SimplePlan(YEAR, [152, 153, 154]))
    assert again.calls == []
    assert by_doy(out) == {152: "banked", 153: "banked", 154: "banked"}


def test_long_blocks_are_chunked_to_bound_the_kept_campaigns() -> None:
    assert chunks([(1, 15)], 6) == [(1, 6), (7, 12), (13, 15)]
    assert chunks([(1, 3), (10, 10)], 6) == [(1, 3), (10, 10)]


def test_the_busiest_day_runs_alone_first_as_the_preflight(env) -> None:
    camp, sol = env
    bsw = FakeBSW(camp, sol)
    plan = SimplePlan(YEAR, list(range(152, 158)), busiest=155)
    go(bsw, plan, preflight=True)
    assert bsw.calls[0] == (155, 1, 3)
    assert [c[:2] for c in bsw.calls[1:]] == [(152, 3), (156, 2)]


def test_a_backend_that_raises_banks_what_finished_and_stops_as_unknown(env) -> None:
    camp, sol = env
    bsw = FakeBSW(camp, sol, raise_on=152)
    out = go(bsw, SimplePlan(YEAR, list(range(152, 156))))
    st = by_doy(out)
    assert all(st[d] == "ok" for d in range(152, 156)), "FINs written before the raise count"
    assert len(bsw.calls) == 1


def test_a_plan_with_problems_is_refused_before_bernese_starts(env) -> None:
    camp, sol = env
    bsw = FakeBSW(camp, sol)
    with pytest.raises(ValueError, match="MAXPAR"):
        go(bsw, SimplePlan(YEAR, [152], problems=["MAXPAR 1000 is below 41 stations"]))
    assert bsw.calls == []


class RecordingLedger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def run_start(self, **kw):
        self.events.append(("run_start", kw))
        return "r1"

    def attempt_start(self, **kw):
        self.events.append(("attempt_start", kw))

    def attempt_end(self, **kw):
        self.events.append(("attempt_end", kw))

    def run_end(self, **kw):
        self.events.append(("run_end", kw))


def test_the_ledger_hears_every_day_in_block_mode(env) -> None:
    camp, sol = env
    led = RecordingLedger()
    go(
        FakeBSW(camp, sol, outcomes={154: "maxpar"}),
        SimplePlan(YEAR, [152, 153, 154, 155, 156, 157]),
        maxsess=2,
        chunk_days=6,
        ledger=led,
    )
    names = [e for e, _ in led.events]
    assert names[0] == "run_start" and names[-1] == "run_end"
    ends = {kw["doy"]: kw for e, kw in led.events if e == "attempt_end"}
    assert ends[154]["outcome"] == "failed" and "neqckdim" in ends[154]["error"]
    assert all(kw["mode"] == "block" for e, kw in led.events if e.startswith("attempt"))
    not_started = [d for d, kw in ends.items() if kw["outcome"] == "not_run"]
    assert not_started, "days queued behind the abort are recorded as not_run"
    assert led.events[-1][1]["halt"]


def test_an_interrupt_records_the_run_end_and_propagates(env) -> None:
    camp, sol = env

    class Interrupting(FakeBSW):
        def run_sessions(self, *a, **kw):
            raise KeyboardInterrupt

    led = RecordingLedger()
    with pytest.raises(KeyboardInterrupt):
        go(Interrupting(camp, sol), SimplePlan(YEAR, [152, 153]), ledger=led)
    assert led.events[-1][0] == "run_end"
    assert "interrupted" in led.events[-1][1]["halt"]


def test_repr_campaign_names_follow_the_bpe_server() -> None:
    """server.cpp: REPR_MODE_CAMPAIGN + YEAR (2 digits) + SESSION."""
    assert repr_campaign_name("PHR", 2025, "1520") == "PHR251520"
    assert repr_campaign_name("LZY", 2025, "0040") == "LZY250040"


# --- the deletion guard -----------------------------------------------------------------


def test_only_a_private_session_campaign_can_be_deleted(tmp_path: Path) -> None:
    from bernese_workflow.run_year import _remove_private_campaign

    (tmp_path / "PHREF").mkdir()
    (tmp_path / "PHR251520").mkdir()
    with pytest.raises(RuntimeError, match="refusing"):
        _remove_private_campaign(tmp_path, "PHREF", "PHREF")
    with pytest.raises(RuntimeError, match="refusing"):
        _remove_private_campaign(tmp_path, "../elsewhere", "PHREF")
    _remove_private_campaign(tmp_path, "PHR251520", "PHREF")
    assert (tmp_path / "PHREF").is_dir() and not (tmp_path / "PHR251520").exists()


# --- the backend's multi-session call ---------------------------------------------------

STATUS = Path(__file__).parent / "fixtures" / "bpe_status"


def test_run_status_files_from_gps3_parse() -> None:
    """Real <PCF>.RUN files: a 20-session REPR run, and a failed single session."""
    from bernese_workflow.backends import parse_run_status

    ok = parse_run_status((STATUS / "LUZON_DLY_multisession_ok.RUN").read_text())
    assert len(ok) == 20 and set(ok.values()) == {"finished"}
    assert "253460" in ok and "253650" in ok
    assert parse_run_status((STATUS / "PHNAT_DLY_error.RUN").read_text()) == {"252000": "error"}


@pytest.mark.skipif(shutil.which("perl") is None, reason="needs perl")
def test_run_sessions_passes_the_driver_its_arguments_and_reads_the_status(tmp_path: Path) -> None:
    from bernese_workflow.backends import LinuxBPEBackend

    P = tmp_path / "P"
    (P / "PHREF" / "BPE").mkdir(parents=True)
    argv_file = tmp_path / "argv"
    driver = tmp_path / "fake_sessions_pcs.pl"
    driver.write_text(
        "#!/usr/bin/perl\n"
        f"open(my $a, '>', '{argv_file}'); print $a join(' ', @ARGV); close($a);\n"
        f"open(my $s, '>', '{P}/PHREF/BPE/PHREF_DLY.RUN');\n"
        'print $s "Status of PHREF_DLY.PCF\\n\\nSession 251520: finished\\nSession 251530: error\\n";\n'
        "close($s); exit 1;\n"
    )
    be = LinuxBPEBackend(
        tmp_path / "X", tmp_path / "U", P, pcf_file="PHREF_DLY", driver_script=driver
    )
    r = be.run_sessions("PHREF", 2025, "1520", 4, maxsess=2, repr_prefix="PHR")
    assert argv_file.read_text() == "2025 1520 PHREF_DLY 4 2 PHREF PHR"
    assert r.statuses == {"251520": "finished", "251530": "error"}
    assert r.success is False


def test_run_sessions_refuses_nonsense_counts(tmp_path: Path) -> None:
    from bernese_workflow.backends import LinuxBPEBackend

    be = LinuxBPEBackend(tmp_path, tmp_path, tmp_path)
    with pytest.raises(ValueError):
        be.run_sessions("PHREF", 2025, "1520", 0, maxsess=2, repr_prefix="PHR")


# --- the command line: lock and signals --------------------------------------------------


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch):
    for v in ("P", "U", "C", "S"):
        (tmp_path / v).mkdir()
        monkeypatch.setenv(v, str(tmp_path / v))
    (tmp_path / "P" / "PHREF" / "BPE").mkdir(parents=True)
    (tmp_path / "S" / "PHREF" / "2025" / "SOL").mkdir(parents=True)
    monkeypatch.setenv("BPE_LOCK", str(tmp_path / "bpe.lock"))
    return tmp_path


ARGS = ["--campaign", "PHREF", "--repr-prefix", "PHR", "--year", "2025",
        "--from", "152", "--to", "153", "--pcf", "PHREF_DLY", "--run"]  # fmt: skip


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigterm_during_a_run_stops_it_cleanly_and_frees_the_lock(cli_env, monkeypatch) -> None:
    """SIGTERM becomes an exception, so the BPE's process-group cleanup and the
    lock release both run on the way out (the #271 recommendation)."""
    import os
    import signal

    import bernese_workflow.run_year as ry
    from bernese_workflow.bpe_lock import BPELock

    def killed(*_a, **_k):
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError("the signal should have interrupted the run")

    monkeypatch.setattr(ry, "run_year", killed)
    before = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
    assert ry.main(ARGS) == 130
    with BPELock(purpose="after"):
        pass  # free again
    assert {s: signal.getsignal(s) for s in before} == before, "handlers are put back"


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl locks are POSIX")
def test_a_second_run_is_refused_while_one_holds_the_lock(cli_env, monkeypatch, capsys) -> None:
    import bernese_workflow.run_year as ry
    from bernese_workflow.bpe_lock import BPELock

    monkeypatch.setattr(ry, "run_year", lambda *a, **k: [])
    with BPELock(purpose="PHREF 2025 the other run"):
        assert ry.main(ARGS) == 3
    assert "the other run" in capsys.readouterr().err
