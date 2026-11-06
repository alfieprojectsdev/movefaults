"""Tests for bernese-notify: who is told what, once, and that a failure is retried.

No network and no Bernese: mail goes to a list, and the queue and ledgers are real
files in a temporary directory, written by the code that writes them in production.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import smtplib
from pathlib import Path

import pytest
from bernese_workflow.ledger import Ledger
from bernese_workflow.notify import (
    Config,
    ConfigError,
    Mail,
    Notifier,
    PartialDelivery,
    load_config,
    main,
    smtp_sender,
    tally,
)
from bernese_workflow.run_queue import PREFLIGHT, START, STOP, Queue, make_request

T0 = dt.datetime(2026, 11, 6, 2, 0, tzinfo=dt.UTC)
BOSS = "boss@example.org"
AB = "ab@example.org"
CD = "cd@example.org"


class Rig:
    def __init__(self, tmp: Path) -> None:
        self.queue = Queue(tmp / "worker").ensure()
        self.savedisk = tmp / "SAVEDISK"
        self.savedisk.mkdir()
        self.now = T0
        self.sent: list[Mail] = []
        self.fail = False
        self.alive = True
        self.pid_alive = True
        self.cfg = Config(
            mail={},
            maintainer=BOSS,
            console_url="https://console",
            operators={"AB": AB, "CD": CD},
            savedisk=self.savedisk,
        )

    def _send(self, m: Mail) -> None:
        if self.fail:
            raise OSError("smtp is down")
        self.sent.append(m)

    def run(self) -> int:
        return Notifier(
            self.cfg,
            self.queue,
            self._send,
            now=lambda: self.now,
            worker_alive=lambda _p: self.alive,
            pid_alive=lambda _h, _p: self.pid_alive,
        ).run()

    def request(self, by: str = "AB", kind: str = START) -> dict:
        return make_request(
            kind, by, at=self.now, campaign="LUZON", year=2026, pcf="LUZON_DLY",
            repr_prefix="LZY", **{"from": 1, "to": 3},
        )  # fmt: skip

    def activate(self, req: dict) -> Path:
        req = {**req, "started": self.now.isoformat()}
        path = self.queue.active / f"{req['id']}.json"
        path.write_text(json.dumps(req))
        return path

    def finish(self, req: dict, outcome: str, detail: str = "") -> None:
        path = self.queue.active / f"{req['id']}.json"
        if not path.exists():
            path = self.activate(req)
        self.queue.finish(path, json.loads(path.read_text()), outcome, detail)

    def ledger(self, *, request: str | None = None, days: tuple[int, ...] = (1, 2, 3)) -> Ledger:
        root = self.savedisk / "LUZON" / "2026"
        root.mkdir(parents=True, exist_ok=True)
        ledger = Ledger(root / "ledger.jsonl")
        extra = {"request": request} if request else {}
        ledger.run_start(campaign="LUZON", year=2026, doys=list(days), banked=[], **extra)
        return ledger

    def subjects(self) -> list[str]:
        return [m.subject for m in self.sent]


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    r = Rig(tmp_path)
    r.run()  # the baseline pass, so each test sees only what it adds
    return r


def test_first_pass_mails_nothing_that_already_exists(tmp_path: Path) -> None:
    r = Rig(tmp_path)
    r.finish(r.request(), "ok")
    r.activate(r.request())
    r.ledger().run_end(halt=None)
    assert r.run() == 0
    assert r.sent == []
    assert r.run() == 0
    assert r.sent == []


def test_started_goes_to_the_person_who_started_it_and_the_maintainer(rig: Rig) -> None:
    rig.activate(rig.request("AB"))
    rig.run()
    assert len(rig.sent) == 1
    assert "started" in rig.sent[0].subject
    assert set(rig.sent[0].to) == {AB, BOSS}


def test_a_message_is_sent_once(rig: Rig) -> None:
    req = rig.request()
    rig.activate(req)
    rig.run()
    rig.run()
    assert len(rig.sent) == 1
    rig.finish(req, "ok")
    rig.run()
    rig.run()
    assert len(rig.sent) == 2


def test_a_failed_send_is_retried_and_reported(rig: Rig) -> None:
    req = rig.request()
    rig.finish(req, "failed", "DOY 002 broke")
    rig.fail = True
    assert rig.run() == 1
    status = json.loads((rig.queue.root / "notify/status.json").read_text())
    assert len(status["errors"]) == 1
    rig.fail = False
    assert rig.run() == 0
    assert len(rig.sent) == 1
    assert "failed" in rig.sent[0].subject
    status = json.loads((rig.queue.root / "notify/status.json").read_text())
    assert status["errors"] == []


def test_someone_with_no_address_is_named_and_the_maintainer_still_hears(rig: Rig) -> None:
    rig.finish(rig.request("ZZ"), "ok")
    rig.run()
    assert rig.sent[0].to == (BOSS,)
    assert "No email address on file for: ZZ" in rig.sent[0].body


def test_failure_mail_names_the_day_message_note_and_link(rig: Rig) -> None:
    req = rig.request()
    ledger = rig.ledger(request=req["id"])
    ledger.attempt_end(doy=1, session="0010", outcome="ok", seconds=10)
    ledger.attempt_end(
        doy=2, session="0020", outcome="failed", seconds=10, error="MAXPAR", note="raise MAXPAR"
    )
    rig.finish(req, "failed", "DOY 002 MAXPAR")
    rig.run()
    body = rig.sent[0].body
    assert "DOY 002: MAXPAR" in body
    assert "raise MAXPAR" in body
    assert "1 solved, 1 failed" in body
    assert "https://console/#/c/LUZON/2026/day/2/failure" in body


def test_whoever_stopped_a_run_is_told_too(rig: Rig) -> None:
    req = rig.request("AB")
    rig.activate(req)
    rig.run()
    rig.sent.clear()
    stop = make_request(STOP, "CD", at=rig.now, target=req["id"])
    path = rig.queue.done / f"{stop['id']}.json"
    path.write_text(json.dumps({**stop, "outcome": "applied", "applied_to": req["id"]}))
    rig.finish(req, "stopped", "stopped by CD")
    rig.run()
    assert len(rig.sent) == 1
    assert set(rig.sent[0].to) == {AB, CD, BOSS}
    assert "Stopped by: CD" in rig.sent[0].body


def test_preflight_mails_only_when_it_ends(rig: Rig) -> None:
    req = rig.request(kind=PREFLIGHT)
    rig.activate(req)
    rig.run()
    assert rig.sent == []
    rig.finish(req, "ok")
    rig.run()
    assert len(rig.sent) == 1


def test_progress_comes_on_the_interval_with_the_days_so_far(rig: Rig) -> None:
    req = rig.request()
    rig.activate(req)
    ledger = rig.ledger(request=req["id"])
    rig.run()
    rig.sent.clear()
    ledger.attempt_end(doy=1, session="0010", outcome="ok", seconds=10)
    os.utime(ledger.path, (rig.now.timestamp(), rig.now.timestamp()))
    rig.now += dt.timedelta(hours=1)
    rig.run()
    assert rig.sent == []
    rig.now = T0 + dt.timedelta(hours=6)
    os.utime(ledger.path, (rig.now.timestamp(), rig.now.timestamp()))
    rig.run()
    assert len(rig.sent) == 1
    assert "still running" in rig.sent[0].subject
    assert "1 solved" in rig.sent[0].body and "2 still to do" in rig.sent[0].body


def test_a_stuck_run_is_reported_once_and_again_only_after_it_moves(rig: Rig) -> None:
    req = rig.request()
    rig.activate(req)
    ledger = rig.ledger(request=req["id"])
    os.utime(ledger.path, (rig.now.timestamp(), rig.now.timestamp()))
    rig.run()
    rig.sent.clear()
    rig.now += dt.timedelta(minutes=121)
    rig.run()
    assert [s for s in rig.subjects() if "stuck" in s]
    rig.sent.clear()
    rig.now += dt.timedelta(minutes=5)
    rig.run()
    assert not [s for s in rig.subjects() if "stuck" in s]
    os.utime(ledger.path, (rig.now.timestamp(), rig.now.timestamp()))
    rig.run()
    rig.now += dt.timedelta(minutes=121)
    rig.run()
    assert [s for s in rig.subjects() if "stuck" in s]


def test_worker_down_waits_then_mails_once_and_resets(rig: Rig) -> None:
    req = rig.request("AB")
    rig.queue.submit(req)
    rig.alive = False
    rig.run()
    assert rig.sent == []
    rig.now += dt.timedelta(minutes=11)
    rig.run()
    assert rig.subjects() == ["[BSW] The run worker is down"]
    assert set(rig.sent[0].to) == {AB, BOSS}
    rig.run()
    assert len(rig.sent) == 1
    rig.alive = True
    rig.run()
    rig.alive = False
    rig.run()
    rig.now += dt.timedelta(minutes=11)
    rig.run()
    assert len(rig.sent) == 2


def test_halted_mails_once_per_reason(rig: Rig) -> None:
    halted = rig.queue.root / "HALTED"
    halted.write_text("first reason\n")
    rig.run()
    rig.run()
    assert len(rig.sent) == 1
    assert "first reason" in rig.sent[0].body
    halted.write_text("second reason\n")
    rig.run()
    assert len(rig.sent) == 2


def test_a_direct_run_tells_only_the_maintainer(rig: Rig) -> None:
    ledger = rig.ledger()
    rig.run()
    assert rig.sent[0].to == (BOSS,)
    assert "direct run started" in rig.sent[0].subject
    ledger.attempt_end(doy=1, session="0010", outcome="ok", seconds=10)
    ledger.run_end(halt=None)
    rig.run()
    assert "direct run finished" in rig.sent[1].subject
    rig.run()
    assert len(rig.sent) == 2


def test_a_direct_run_that_died_is_reported(rig: Rig) -> None:
    rig.ledger()
    rig.run()
    rig.pid_alive = False
    rig.run()
    assert "direct run died" in rig.sent[1].subject


def test_a_direct_run_that_hangs_is_reported_once_as_stuck(rig: Rig) -> None:
    ledger = rig.ledger()
    os.utime(ledger.path, (rig.now.timestamp(), rig.now.timestamp()))
    rig.run()
    rig.sent.clear()
    rig.now += dt.timedelta(minutes=121)
    rig.run()
    rig.run()
    stuck = [m for m in rig.sent if "stuck" in m.subject]
    assert len(stuck) == 1
    assert stuck[0].to == (BOSS,)


def test_a_direct_run_older_than_the_baseline_is_history_when_it_appears(tmp_path: Path) -> None:
    """SAVEDISK wasn't there at the first pass: its old runs mustn't all be mailed later."""
    r = Rig(tmp_path)
    r.now = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    r.run()
    r.ledger()
    r.run()
    r.run()
    assert r.sent == []


def test_a_missing_savedisk_is_reported_not_read_as_no_runs(tmp_path: Path) -> None:
    r = Rig(tmp_path)
    r.savedisk.rmdir()
    assert r.run() == 1
    status = json.loads((r.queue.root / "notify/status.json").read_text())
    assert "SAVEDISK" in status["errors"][0]


def test_a_partial_delivery_is_reported_and_not_sent_again(rig: Rig) -> None:
    rig.finish(rig.request(), "ok")
    attempts = []

    def refuse(m: Mail) -> None:
        attempts.append(m)
        raise PartialDelivery("refused: ab@example.org")

    rig._send = refuse  # type: ignore[method-assign]
    assert rig.run() == 1
    status = json.loads((rig.queue.root / "notify/status.json").read_text())
    assert "refused" in status["errors"][0]
    assert rig.run() == 0
    assert len(attempts) == 1


def test_a_pass_already_running_means_this_one_does_nothing(rig: Rig) -> None:
    rig.finish(rig.request(), "ok")
    with open(rig.queue.root / "notify/lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert rig.run() == 0
        assert rig.sent == []
    rig.run()
    assert len(rig.sent) == 1


def test_a_worker_down_message_is_saved_before_anything_later_can_fail(rig: Rig) -> None:
    rig.alive = False
    rig.run()
    rig.now += dt.timedelta(minutes=11)
    rig.ledger()  # a direct run, so _direct has a message to send after _worker's

    def fail_on_direct(m: Mail) -> None:
        if "direct" in m.subject:
            raise SystemExit("killed mid-pass")
        rig.sent.append(m)

    rig._send = fail_on_direct  # type: ignore[method-assign]
    with pytest.raises(SystemExit):
        rig.run()
    state = json.loads((rig.queue.root / "notify/state.json").read_text())
    assert state["worker"]["sent"] is True


def test_worker_down_mail_survives_a_queue_file_that_is_not_a_request(rig: Rig) -> None:
    (rig.queue.queue / "junk.json").write_text("[]")
    rig.alive = False
    rig.run()
    rig.now += dt.timedelta(minutes=11)
    rig.run()
    assert rig.subjects() == ["[BSW] The run worker is down"]


def test_a_queued_run_is_not_also_reported_as_direct(rig: Rig) -> None:
    req = rig.request()
    rig.activate(req)
    rig.ledger(request=req["id"])
    rig.run()
    assert not [s for s in rig.subjects() if "direct" in s]


def test_a_damaged_state_is_kept_aside_and_mails_no_history(rig: Rig) -> None:
    rig.finish(rig.request(), "ok")
    state = rig.queue.root / "notify/state.json"
    state.write_text("{not json")
    assert rig.run() == 0
    assert rig.sent == []
    assert state.with_suffix(".damaged").exists()


def test_tally_uses_each_days_latest_attempt(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    run = ledger.run_start(campaign="X", year=2026, doys=[1, 2], banked=[])
    ledger.attempt_end(doy=1, session="0010", outcome="failed", seconds=1)
    ledger.attempt_end(doy=1, session="0010", outcome="ok", seconds=1)
    entries = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    t = tally(entries, run)
    assert (t.ok, len(t.failed), t.left) == (1, 0, 1)


def test_tally_does_not_count_banked_days_as_still_to_do(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    run = ledger.run_start(campaign="X", year=2026, doys=[1, 2, 3], banked=[1, 2])
    ledger.attempt_end(doy=3, session="0030", outcome="ok", seconds=1)
    entries = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    t = tally(entries, run)
    assert t.left == 0
    assert "2 already solved" in t.line()


# --- products ---------------------------------------------------------------------


def _products(rig: Rig, **fields: object) -> None:
    d = rig.queue.root / "products"
    d.mkdir(exist_ok=True)
    (d / "status.json").write_text(json.dumps({"last_pass": rig.now.isoformat(), **fields}))


def test_products_stay_quiet_when_not_installed_or_nothing_is_wrong(rig: Rig) -> None:
    rig.run()
    _products(rig, errors=[], late=[], config=[{"file": "DATUM.BSW", "out_of_date": False}])
    rig.run()
    assert rig.sent == []


def test_a_product_problem_mails_the_maintainer_once_until_it_changes(rig: Rig) -> None:
    _products(rig, errors=["a.gz: OSError: reset"])
    rig.run()
    rig.run()
    assert len(rig.sent) == 1
    assert rig.sent[0].to == (BOSS,)
    assert "a.gz" in rig.sent[0].body
    _products(rig, errors=["b.gz: OSError: reset"])
    rig.run()
    assert len(rig.sent) == 2


def test_an_out_of_date_file_is_reported_as_unchanged(rig: Rig) -> None:
    _products(
        rig,
        config=[
            {
                "file": "SATELLIT_I20.SAT",
                "out_of_date": True,
                "local_size": 1,
                "local_date": "2024-10-22",
                "aiub_size": 2,
                "aiub_date": "2026-10-20",
            }
        ],
    )
    rig.run()
    assert "SATELLIT_I20.SAT" in rig.sent[0].body
    assert "Nothing was changed" in rig.sent[0].body


def test_a_nightly_fetch_that_stopped_is_reported(rig: Rig) -> None:
    _products(rig)
    rig.now += dt.timedelta(days=3)
    rig.run()
    assert "last ran 3 days ago" in rig.sent[0].body


# --- configuration ----------------------------------------------------------------


def _write_config(tmp: Path, *, operators: str = 'AB = "ab@example.org"') -> Path:
    conf = tmp / "mail.conf"
    conf.write_text(
        "MAIL_URL=smtps://smtp.example.org:465\nMAIL_FROM=a@example.org\n"
        "MAIL_TO=boss@example.org\nMAIL_USER=a@example.org\nMAIL_PASS='secret'\n"
    )
    conf.chmod(0o600)
    toml = tmp / "notify.toml"
    toml.write_text(f'mail_conf = "{conf}"\n\n[operators]\n{operators}\n')
    toml.chmod(0o600)
    return toml


def test_config_reads_the_existing_mail_file(tmp_path: Path) -> None:
    cfg = load_config(_write_config(tmp_path))
    assert cfg.maintainer == BOSS
    assert cfg.operators == {"AB": AB}
    assert cfg.mail["MAIL_PASS"] == "secret"


@pytest.mark.parametrize("name", ["notify.toml", "mail.conf"])
def test_config_refuses_a_file_others_can_read(tmp_path: Path, name: str) -> None:
    path = _write_config(tmp_path)
    (tmp_path / name).chmod(0o644)
    with pytest.raises(ConfigError, match="chmod 600"):
        load_config(path)


def test_config_refuses_a_bad_address_without_quoting_secrets(tmp_path: Path) -> None:
    path = _write_config(tmp_path, operators='AB = "not an address"')
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "secret" not in str(exc.value)


# --- the real send function, against a fake server ---------------------------------


class FakeSMTP:
    refused: dict = {}
    sent: list = []

    def __init__(self, *_a: object, **_k: object) -> None:
        pass

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *_a: object) -> None:
        pass

    def login(self, *_a: object) -> None:
        pass

    def send_message(self, msg: object) -> dict:
        FakeSMTP.sent.append(msg)
        return FakeSMTP.refused


MAIL = {
    "MAIL_URL": "smtps://smtp.example.org:465",
    "MAIL_FROM": "BSW <a@example.org>",
    "MAIL_USER": "a@example.org",
    "MAIL_PASS": "secret",
}


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(FakeSMTP, "refused", {})
    monkeypatch.setattr(FakeSMTP, "sent", [])
    return FakeSMTP


def test_a_message_carries_a_date_and_a_message_id(fake_smtp: type[FakeSMTP]) -> None:
    smtp_sender(MAIL)(Mail((BOSS,), "s", "b\n"))
    msg = fake_smtp.sent[0]
    assert msg["Date"]
    assert msg["Message-ID"].endswith("@example.org>")


def test_a_recipient_refused_beside_an_accepted_one_is_not_silent(
    fake_smtp: type[FakeSMTP], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fake_smtp, "refused", {AB: (550, b"no such user")})
    with pytest.raises(PartialDelivery, match=AB):
        smtp_sender(MAIL)(Mail((BOSS, AB), "s", "b\n"))


# --- --dry-run ----------------------------------------------------------------------


def test_dry_run_says_when_it_has_nothing_to_show_and_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("S", str(tmp_path))
    state_dir = tmp_path / "worker"
    damaged = state_dir / "notify/state.json"
    damaged.parent.mkdir(parents=True)
    damaged.write_text("{not json")
    config = str(_write_config(tmp_path))
    assert main(["--config", config, "--state", str(state_dir), "--dry-run"]) == 0
    assert "first pass" in capsys.readouterr().out
    assert damaged.read_text() == "{not json"
    assert not (state_dir / "notify/status.json").exists()


def test_config_refuses_a_limit_that_isnt_a_number(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    path.write_text('stall_minutes = "soon"\n' + path.read_text())
    with pytest.raises(ConfigError, match="must be numbers"):
        load_config(path)
