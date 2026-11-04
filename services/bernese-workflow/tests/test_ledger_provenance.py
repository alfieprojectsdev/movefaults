"""The run ledger's provenance (who, command, code, PCF, products, exclusions)
and its halt reason, and that ledgers written before either still read.

The console (services/bsw-console) showed "not recorded by the service yet"
for the first set, and reported a run stopped by the pre-BPE header check as
"unknown failure" while its known-errors screen counted no failure at all.
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from bernese_workflow import ledger as ledger_mod
from bernese_workflow.backends import BPEResult, LinuxBPEBackend
from bernese_workflow.ledger import (
    Ledger,
    code_version,
    halt_reason,
    read_entries,
    run_status,
    started_by,
)
from bernese_workflow.month_driver import run_days
from bernese_workflow.rinex_header_validator import (
    Mismatch,
    PreflightUnavailable,
    ValidationError,
    ValidationReport,
)
from bernese_workflow.run_plan import Excluded, RunPlan
from bernese_workflow.run_year import SimplePlan, run_year

FIXTURES = Path(__file__).parent / "fixtures"
OLD_LEDGER = FIXTURES / "ledger_v1_before_provenance.jsonl"
MAXPAR = FIXTURES / "bpe_errors" / "MXPREP_MX230100_511_000"
YEAR = 2025

BAD_HEADER = ValidationReport(
    mismatches=[Mismatch("BOST", "receiver", "TRIMBLE NETR9", "LEICA GR50")]
)


def _only(entries: list[dict], event: str) -> dict:
    (e,) = [x for x in entries if x["event"] == event]
    return e


# --- provenance in run_start ----------------------------------------------------------


def test_run_start_records_who_what_and_which_code(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["bernese-run-year", "--campaign", "PHREF", "--run"])
    monkeypatch.setattr(ledger_mod.getpass, "getuser", lambda: "gps3")
    monkeypatch.setenv("SUDO_USER", "operator")
    led = Ledger(tmp_path / "l.jsonl")
    led.run_start(
        campaign="PHREF", year=YEAR, doys=[152], banked=[], config="abc",
        pcf="PHREF_DLY", products="COD0OPSFIN", product_tier="final",
        excluded=[{"doy": 151, "reason": "short", "detail": "2 reference station(s)"}],
    )  # fmt: skip
    start = _only(read_entries(tmp_path / "l.jsonl")[0], "run_start")
    assert (start["user"], start["sudo_user"]) == ("gps3", "operator")
    assert start["command"] == ["bernese-run-year", "--campaign", "PHREF", "--run"]
    assert (start["pcf"], start["products"], start["product_tier"]) == (
        "PHREF_DLY",
        "COD0OPSFIN",
        "final",
    )
    assert start["excluded"] == [
        {"doy": 151, "reason": "short", "detail": "2 reference station(s)"}
    ]
    # This test runs from the repository, so the version is real.
    head = subprocess.run(
        ["git", "-C", str(Path(ledger_mod.__file__).parent), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert start["code"]["commit"] == head
    assert start["code"]["dirty"] in (True, False)


def test_run_start_writes_extra_fields_as_given(tmp_path: Path) -> None:
    """The run worker (#316) adds who asked for a run through ``extra``."""
    led = Ledger(tmp_path / "l.jsonl")
    led.run_start(campaign="PHREF", year=YEAR, doys=[152], banked=[], pcf="PHREF_DLY",
                  request="q1", kind="range", submitted_by="console", reason="")  # fmt: skip
    start = _only(read_entries(tmp_path / "l.jsonl")[0], "run_start")
    assert (start["request"], start["kind"], start["submitted_by"]) == ("q1", "range", "console")
    assert start["pcf"] == "PHREF_DLY" and start["run"] == led.run_id


@pytest.mark.parametrize("name", ["run", "ts", "event", "host", "user", "code"])
def test_run_start_extra_may_not_reuse_a_written_field(tmp_path: Path, name: str) -> None:
    led = Ledger(tmp_path / "l.jsonl")
    with pytest.raises(ValueError, match=name):
        led.run_start(campaign="X", year=YEAR, doys=[1], banked=[], **{name: "spoof"})
    assert not (tmp_path / "l.jsonl").exists(), "nothing is written"


def test_the_reserved_set_matches_what_run_start_writes(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "l.jsonl")
    led.run_start(campaign="X", year=YEAR, doys=[1], banked=[])
    start = _only(read_entries(tmp_path / "l.jsonl")[0], "run_start")
    assert set(start) == ledger_mod._RUN_START_FIELDS


def test_without_sudo_the_sudo_user_is_null(monkeypatch) -> None:
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setattr(ledger_mod.getpass, "getuser", lambda: "gps3")
    assert started_by() == {"user": "gps3", "sudo_user": None}


def test_no_login_name_is_unknown_not_a_failed_run(monkeypatch) -> None:
    def nobody():
        raise OSError("No username set in the environment")

    monkeypatch.setattr(ledger_mod.getpass, "getuser", nobody)
    assert started_by()["user"] == "unknown"


def test_a_directory_outside_any_checkout_has_an_unknown_version(tmp_path: Path) -> None:
    assert code_version(tmp_path) == {"commit": "unknown", "dirty": None}


def test_no_git_at_all_is_an_unknown_version(monkeypatch) -> None:
    def no_git(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(ledger_mod.subprocess, "run", no_git)
    assert code_version() == {"commit": "unknown", "dirty": None}


def test_a_hung_git_is_an_unknown_version(monkeypatch) -> None:
    def hung(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    monkeypatch.setattr(ledger_mod.subprocess, "run", hung)
    assert code_version() == {"commit": "unknown", "dirty": None}


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_dirty_follows_tracked_files_not_untracked_ones(tmp_path: Path) -> None:
    def git(*a: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "a.py").write_text("x = 1\n")
    git("add", "a.py")
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "one")
    clean = code_version(tmp_path)
    assert len(str(clean["commit"])) == 40 and clean["dirty"] is False
    (tmp_path / "scratch.txt").write_text("notes")
    assert code_version(tmp_path)["dirty"] is False, "an untracked file is not imported"
    (tmp_path / "a.py").write_text("x = 2\n")
    assert code_version(tmp_path)["dirty"] is True


def test_run_days_records_the_process_facts_and_nulls_for_the_plan(tmp_path: Path) -> None:
    """month_driver has no PCF and no plan of its own: those are null, not guessed."""
    (tmp_path / "BPE").mkdir()

    class Ok:
        def run(self, campaign, year, session):
            with gzip.open(tmp_path / f"FIN_{year}{session}.NQ0.gz", "wb") as f:
                f.write(b"x")
            return BPEResult(True, None, None, False, False)

    led = Ledger(tmp_path / "l.jsonl")
    run_days(Ok(), "LUZON", YEAR, [1], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE", ledger=led)
    entries = read_entries(tmp_path / "l.jsonl")[0]
    start = _only(entries, "run_start")
    assert start["user"] and start["command"] and start["code"]["commit"]
    assert start["pcf"] is None and start["product_tier"] is None and start["excluded"] is None
    end = _only(entries, "run_end")
    assert end["halt"] is None and end["halt_reason"] is None


# --- what run_year records ------------------------------------------------------------


class Recording:
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

    def ends(self) -> dict[int, dict]:
        return {kw["doy"]: kw for e, kw in self.events if e == "attempt_end"}


class Sessions:
    """A run_sessions backend: every day ok except ``maxpar`` days, which leave
    the real MAXPAR step output and stop the queue (NEXTSESS=0)."""

    def __init__(self, camp: Path, sol: Path, maxpar=(), raises: Exception | None = None):
        self.camp, self.sol, self.maxpar, self.raises = camp, sol, set(maxpar), raises
        self.calls = 0

    def run_sessions(self, campaign, year, first_session, n, *, maxsess, repr_prefix):
        from bernese_workflow.backends import SessionsResult, repr_campaign_name

        self.calls += 1
        if self.raises is not None:
            raise self.raises
        first = int(first_session[:3])
        statuses = {}
        for doy in range(first, first + n):
            s = f"{doy:03d}0"
            tag = f"{year % 100:02d}{s}"
            bpe = self.camp / repr_campaign_name(repr_prefix, year, s) / "BPE"
            bpe.mkdir(parents=True, exist_ok=True)
            if doy in self.maxpar:
                for suffix in (".PRT", ".LOG"):
                    shutil.copyfile(
                        MAXPAR.with_suffix(suffix), (bpe / f"RP{tag}_511_000").with_suffix(suffix)
                    )
                statuses[tag] = "error"
                break
            with gzip.open(self.sol / f"FIN_{year}{s}.NQ0.gz", "wb") as f:
                f.write(b"NEQ")
            statuses[tag] = "finished"
        return SessionsResult(success=not self.maxpar, raw_log="", statuses=statuses)


@pytest.fixture
def dirs(tmp_path: Path):
    camp, sol = tmp_path / "P", tmp_path / "S" / "SOL"
    (camp / "PHREF" / "BPE").mkdir(parents=True)
    sol.mkdir(parents=True)
    return camp, sol


def go(backend, plan, camp: Path, sol: Path, led, **kw):
    return run_year(
        backend, plan, campaign="PHREF", repr_prefix="PHR", campaign_dir=camp,
        sol_dir=sol, maxsess=3, preflight=False, ledger=led, **kw,
    )  # fmt: skip


def test_run_year_records_the_plans_exclusions_with_their_reasons(dirs) -> None:
    camp, sol = dirs
    plan = RunPlan(
        year=YEAR,
        todo=[153, 154],
        excluded=[
            Excluded(151, "solved"),
            Excluded(152, "short", "2 reference station(s): AAAA BBBB"),
            Excluded(155, "listed", "receiver swap"),
        ],
    )
    led = Recording()
    go(Sessions(camp, sol), plan, camp, sol, led,
       pcf="PHREF_DLY", products="COD0OPSFIN", product_tier="final")  # fmt: skip
    start = led.events[0][1]
    assert start["excluded"] == [
        {"doy": 151, "reason": "solved", "detail": ""},
        {"doy": 152, "reason": "short", "detail": "2 reference station(s): AAAA BBBB"},
        {"doy": 155, "reason": "listed", "detail": "receiver swap"},
    ]
    assert (start["pcf"], start["products"], start["product_tier"]) == (
        "PHREF_DLY", "COD0OPSFIN", "final",
    )  # fmt: skip
    assert led.events[-1] == ("run_end", {"halt": None, "reason": None})


def test_a_plan_with_nothing_excluded_records_an_empty_list_not_null(dirs) -> None:
    camp, sol = dirs
    led = Recording()
    go(Sessions(camp, sol), SimplePlan(YEAR, [152]), camp, sol, led)
    assert led.events[0][1]["excluded"] == []


def test_a_breaker_halt_records_the_failed_days_label(dirs) -> None:
    camp, sol = dirs
    led = Recording()
    go(Sessions(camp, sol, maxpar={153}), SimplePlan(YEAR, [152, 153, 154]), camp, sol, led)
    end = led.events[-1][1]
    assert "configuration error" in end["halt"]
    assert end["reason"] == {"kind": "breaker", "label": led.ends()[153]["error"], "doy": 153}
    assert end["reason"]["label"] == "neqckdim: DIMENSION_TOO_SMALL"


def test_a_backend_raise_is_recorded_as_backend_not_as_the_breaker(dirs) -> None:
    camp, sol = dirs
    led = Recording()
    go(Sessions(camp, sol, raises=RuntimeError("BPE timed out after 7200s")),
       SimplePlan(YEAR, [152, 153]), camp, sol, led)  # fmt: skip
    end = led.events[-1][1]
    assert end["halt"].startswith("unknown failure (backend raised RuntimeError")
    assert end["reason"] == {"kind": "backend", "label": "backend raised RuntimeError", "doy": None}


def test_a_timeout_after_sessions_started_is_still_backend(dirs) -> None:
    """A killed BPE leaves its sessions failed with no step error, which the
    breaker halts on as unknown; the raise is still the reason, as in run_days."""
    camp, sol = dirs

    class Timeout:
        def run_sessions(self, campaign, year, first_session, n, *, maxsess, repr_prefix):
            from bernese_workflow.backends import repr_campaign_name

            (camp / repr_campaign_name(repr_prefix, year, first_session) / "BPE").mkdir(
                parents=True
            )
            raise RuntimeError("BPE timed out after 7200s")

    led = Recording()
    go(Timeout(), SimplePlan(YEAR, [152, 153]), camp, sol, led)
    assert led.ends()[152]["outcome"] == "failed"
    end = led.events[-1][1]
    assert end["reason"] == {"kind": "backend", "label": "backend raised RuntimeError", "doy": None}


# --- a validator halt -----------------------------------------------------------------


def test_a_header_refusal_is_a_failed_day_and_a_validation_halt(dirs) -> None:
    camp, sol = dirs
    led = Recording()
    bsw = Sessions(camp, sol, raises=ValidationError(BAD_HEADER, session="1530"))
    out = go(bsw, SimplePlan(YEAR, [152, 153, 154]), camp, sol, led)
    label = "RINEX header check: 1 receiver/antenna mismatch(es)"
    ends = led.ends()
    # The day it refused is a failure with the validator's label, so a screen
    # counting failures and the run's own halt name the same thing.
    assert (ends[153]["outcome"], ends[153]["error"]) == ("failed", label)
    assert "BOST" in ends[153]["note"]
    assert ends[152]["outcome"] == ends[154]["outcome"] == "not_run"
    end = led.events[-1][1]
    assert end["reason"] == {"kind": "validation", "label": label, "doy": 153}
    assert "unknown failure" not in end["halt"]
    assert end["halt"] == f"pre-BPE validation refused DOY 153 ({label}); no BPE was started"
    assert {o.doy: o.status for o in out} == {152: "not_run", 153: "failed", 154: "not_run"}
    assert bsw.calls == 1


def test_a_header_check_that_cannot_run_is_a_validation_halt_too(dirs) -> None:
    camp, sol = dirs
    led = Recording()
    bsw = Sessions(camp, sol, raises=PreflightUnavailable("no STA", session="1520"))
    go(bsw, SimplePlan(YEAR, [152, 153]), camp, sol, led)
    assert led.events[-1][1]["reason"] == {
        "kind": "validation", "label": "RINEX header check could not run", "doy": 152,
    }  # fmt: skip
    assert led.ends()[152]["error"] == "RINEX header check could not run"


def test_the_real_backend_names_the_session_it_refused_and_starts_no_bpe(
    tmp_path: Path, monkeypatch
) -> None:
    """LinuxBPEBackend.run_sessions validates every session before Perl starts;
    only the validator's verdict is faked here."""
    import bernese_workflow.backends as backends
    import bernese_workflow.rinex_header_validator as rhv

    camp, sol, src = tmp_path / "P", tmp_path / "S" / "SOL", tmp_path / "D" / "RINEX"
    for d in (camp / "PHREF" / "BPE", sol, src):
        d.mkdir(parents=True)
    sta = tmp_path / "D" / "PHR.STA"
    sta.write_text("")
    # DOY 152 passes; DOY 153 is refused.
    monkeypatch.setattr(
        rhv,
        "validate_rinex_headers",
        lambda *a, day, **k: BAD_HEADER if day.timetuple().tm_yday == 153 else ValidationReport(),
    )
    monkeypatch.setattr(
        backends, "_run_bpe_process", lambda *a, **k: pytest.fail("the BPE must not start")
    )
    backend = LinuxBPEBackend(
        tmp_path / "BERN54", tmp_path / "U", camp, pcf_file="PHREF_DLY",
        rinex_source_dir=src, sta_file=sta, preflight_required=True,
    )  # fmt: skip
    led = Ledger(tmp_path / "l.jsonl")
    run_year(backend, SimplePlan(YEAR, [152, 153, 154]), campaign="PHREF", repr_prefix="PHR",
             campaign_dir=camp, sol_dir=sol, maxsess=3, preflight=False, ledger=led)  # fmt: skip
    entries = read_entries(tmp_path / "l.jsonl")[0]
    end = _only(entries, "run_end")
    assert end["halt_reason"]["kind"] == "validation" and end["halt_reason"]["doy"] == 153
    st = run_status(entries)
    assert st.state == "halted"
    assert any("failed DOY 153: RINEX header check" in line for line in st.lines)


def test_run_days_records_a_header_refusal_with_the_validators_label(tmp_path: Path) -> None:
    """Before, the day's error read "no failed BPE step" and the halt "unknown failure"."""
    (tmp_path / "BPE").mkdir()

    class Refuses:
        def run(self, campaign, year, session):
            raise ValidationError(BAD_HEADER, session=session)

    led = Ledger(tmp_path / "l.jsonl")
    out = run_days(Refuses(), "LUZON", YEAR, [1, 2], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE",
                   ledger=led)  # fmt: skip
    label = "RINEX header check: 1 receiver/antenna mismatch(es)"
    assert (out[0].status, out[0].error) == ("failed", label)
    assert out[1].status == "not_run"
    entries = read_entries(tmp_path / "l.jsonl")[0]
    assert _only(entries, "attempt_end")["error"] == label
    end = _only(entries, "run_end")
    assert end["halt_reason"] == {"kind": "validation", "label": label, "doy": 1}
    assert "unknown failure" not in end["halt"]


def test_run_days_records_a_breaker_halt(tmp_path: Path) -> None:
    (tmp_path / "BPE").mkdir()

    class Maxpar:
        def run(self, campaign, year, session):
            for suffix in (".PRT", ".LOG"):
                shutil.copyfile(
                    MAXPAR.with_suffix(suffix),
                    (tmp_path / "BPE" / f"RP{year % 100:02d}{session}_511_000").with_suffix(suffix),
                )
            return BPEResult(False, None, None, False, False)

    led = Ledger(tmp_path / "l.jsonl")
    run_days(Maxpar(), "LUZON", YEAR, [1, 2], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE",
             ledger=led)  # fmt: skip
    end = _only(read_entries(tmp_path / "l.jsonl")[0], "run_end")
    assert end["halt_reason"] == {
        "kind": "breaker", "label": "neqckdim: DIMENSION_TOO_SMALL", "doy": 1,
    }  # fmt: skip


def test_an_interrupt_is_recorded_as_interrupted(dirs) -> None:
    camp, sol = dirs
    led = Recording()
    with pytest.raises(KeyboardInterrupt):
        go(Sessions(camp, sol, raises=KeyboardInterrupt()), SimplePlan(YEAR, [152]), camp, sol, led)
    assert led.events[-1][1]["reason"] == {
        "kind": "interrupted", "label": "KeyboardInterrupt", "doy": None,
    }  # fmt: skip


def test_halt_reason_refuses_a_kind_nobody_reads() -> None:
    with pytest.raises(ValueError, match="unknown halt kind"):
        halt_reason("mystery", "x")


# --- old ledgers still read -----------------------------------------------------------


def test_a_ledger_written_before_provenance_still_reads() -> None:
    """The fixture was written by ledger.Ledger as it was before these fields
    (main at e291737); only host, pid and timestamps were then made generic."""
    entries, bad = read_entries(OLD_LEDGER)
    assert bad == 0 and len(entries) == 14
    assert all(e["v"] == 1 for e in entries)
    assert not any("user" in e or "halt_reason" in e for e in entries), "really the old format"

    first = run_status([e for e in entries if e["run"] == entries[0]["run"]])
    assert first.state == "finished" and first.exit_code == 1
    assert "ok 3" in "\n".join(first.lines)

    latest = run_status(entries)  # the most recent run in the file
    assert latest.state == "halted"
    text = "\n".join(latest.lines)
    assert "HALTED: configuration error (neqckdim: DIMENSION_TOO_SMALL)" in text
    assert "failed DOY 155: neqckdim: DIMENSION_TOO_SMALL" in text
    assert "by " not in text and "excluded by the plan" not in text, "nothing invented"


def test_old_and_new_lines_read_together(tmp_path: Path) -> None:
    """Appending to a ledger an older version wrote, as the next run will."""
    path = tmp_path / "ledger.jsonl"
    shutil.copyfile(OLD_LEDGER, path)
    led = Ledger(path)
    led.run_start(campaign="PHREF", year=YEAR, doys=[157], banked=[], pcf="PHREF_DLY",
                  products="COD0OPSFIN", product_tier="final", excluded=[])  # fmt: skip
    led.run_end(halt=None)
    entries, bad = read_entries(path)
    assert bad == 0 and len(entries) == 16
    st = run_status(entries)
    assert st.state == "finished"
    text = "\n".join(st.lines)
    assert "PCF PHREF_DLY" in text and "products COD0OPSFIN (final)" in text
    assert "0 excluded by the plan" in text
    for line in path.read_text().splitlines():
        json.loads(line)
