"""Email the person who started a run: started, still running, finished, in trouble.

WHY THIS IS A SEPARATE PROCESS
A dead or stuck worker can't report itself, and that is the failure people most
need to hear about. So this runs from cron and only reads what the worker and
the ledgers leave behind: the queue, HALTED, status.json and ledger.jsonl. A mail
failure therefore can't touch a run, and a stalled run can still be reported.

WHO GETS WHAT
A queued run mails the person who submitted it, anyone who stopped it, and the
maintainer. A run started directly with bernese-run-year goes through no queue
and runs as the shared account, so it mails the maintainer only. Someone with no
address in the file is named in the message, which still goes to the maintainer.

NOTHING SENT TWICE, NOTHING LOST
State is <worker state>/notify/state.json, written after each message that was
accepted. A message that fails is not recorded, so the next pass sends it again.
A message some recipients refused and others accepted is recorded as sent, since a
retry would mail the others again, and the refusal is reported. A flock on
notify/lock keeps a slow pass and the next cron pass from sending the same messages.
The first pass only records what already exists, so installing this doesn't mail
the whole history; a direct run that started before that pass and only appears
later (SAVEDISK wasn't mounted, say) is recorded and not mailed either.
<worker state>/notify/status.json says how the last pass went, for the console to
show, because silence must not be mistaken for "all fine". It names the operators
who have an address, not the addresses, so the console can say who won't be told.

CONFIGURATION
~/.config/bernese-workflow/notify.toml, chmod 600. It isn't in the repository,
because this one is public and the file holds people's addresses:

    mail_conf = "~/.luzon_mail.conf"   # MAIL_URL, MAIL_FROM, MAIL_USER, MAIL_PASS, MAIL_TO
    console_url = "https://<host>:8443"
    # maintainer = "..."               # defaults to MAIL_TO
    # progress_hours = 6
    # stall_minutes = 120
    # worker_down_minutes = 10
    # savedisk = "~/GPSDATA/SAVEDISK"  # defaults to $S, then to this

    [operators]
    AB = "ab@example.org"
"""

from __future__ import annotations

import argparse
import collections.abc
import datetime as dt
import email.utils
import fcntl
import hashlib
import json
import os
import smtplib
import ssl
import sys
import tomllib
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

from .ledger import _pid_alive, read_entries
from .run_queue import (
    PREFLIGHT,
    RUN_KINDS,
    STOP,
    Queue,
    default_state_dir,
    now_utc,
    read_json,
    write_json_atomic,
)

DEFAULT_CONFIG = Path.home() / ".config/bernese-workflow/notify.toml"
SUBJECT_PREFIX = "[BSW]"


class ConfigError(ValueError):
    """The configuration can't be used. The message says why, without any secret."""


class PartialDelivery(Exception):
    """The server took a message for some recipients and refused others."""


@dataclass(frozen=True)
class Mail:
    to: tuple[str, ...]
    subject: str
    body: str


@dataclass
class Config:
    mail: dict[str, str]
    maintainer: str
    console_url: str = ""
    operators: dict[str, str] = field(default_factory=dict)
    progress_hours: float = 6.0
    stall_minutes: float = 120.0
    worker_down_minutes: float = 10.0
    savedisk: Path | None = None


def _private(path: Path) -> None:
    mode = path.stat().st_mode
    if mode & 0o077:
        raise ConfigError(f"{path} must be readable only by its owner: chmod 600 {path}")


def _read_mail_conf(path: Path) -> dict[str, str]:
    """KEY=VALUE lines, as luzon_status.sh sources them."""
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.removeprefix("export ").strip()] = value.strip().strip("'\"")
    return out


def _address(text: object, where: str) -> str:
    if not (
        isinstance(text, str)
        and "@" in text
        and not any(c.isspace() or ord(c) < 32 for c in text)
    ):
        raise ConfigError(f"{where} is not an email address")
    return text


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    if not path.exists():
        raise ConfigError(f"{path} doesn't exist: see the notes at the top of notify.py")
    _private(path)
    raw = tomllib.loads(path.read_text())
    conf_path = Path(str(raw.get("mail_conf", ""))).expanduser()
    if not conf_path.is_file():
        raise ConfigError(f"mail_conf {conf_path} doesn't exist")
    _private(conf_path)
    mail = _read_mail_conf(conf_path)
    missing = [k for k in ("MAIL_URL", "MAIL_FROM", "MAIL_USER", "MAIL_PASS") if not mail.get(k)]
    if missing:
        raise ConfigError(f"{conf_path} has no {', '.join(missing)}")
    maintainer = _address(raw.get("maintainer") or mail.get("MAIL_TO"), "the maintainer's address")
    operators = {
        str(k).upper(): _address(v, f"the address for {k}")
        for k, v in dict(raw.get("operators", {})).items()
    }
    # Cron doesn't source LOADGPS.setvar, so $S alone would silently lose every ledger.
    try:
        limits = {k: float(raw.get(k, d)) for k, d in
                  (("progress_hours", 6), ("stall_minutes", 120), ("worker_down_minutes", 10))}
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path}: progress_hours, stall_minutes and worker_down_minutes must be numbers") from exc
    savedisk = raw.get("savedisk") or os.environ.get("S") or Path.home() / "GPSDATA/SAVEDISK"
    return Config(
        mail=mail,
        maintainer=maintainer,
        console_url=str(raw.get("console_url", "")).rstrip("/"),
        operators=operators,
        progress_hours=limits["progress_hours"],
        stall_minutes=limits["stall_minutes"],
        worker_down_minutes=limits["worker_down_minutes"],
        savedisk=Path(str(savedisk)).expanduser(),
    )


def smtp_sender(mail: dict[str, str]) -> collections.abc.Callable[[Mail], None]:
    """A send function using the account in ``mail``. smtps:// or smtp:// with STARTTLS."""
    url = urlparse(mail["MAIL_URL"])
    if url.scheme not in ("smtps", "smtp") or not url.hostname:
        raise ConfigError("MAIL_URL must be smtps://host:port or smtp://host:port")
    # From the sender, because make_msgid's default asks DNS for this host's name.
    domain = email.utils.parseaddr(mail["MAIL_FROM"])[1].rpartition("@")[2] or None

    def send(m: Mail) -> None:
        msg = EmailMessage()
        msg["From"] = mail["MAIL_FROM"]
        msg["To"] = ", ".join(m.to)
        msg["Subject"] = m.subject
        # EmailMessage adds neither, and a receiving server may refuse mail without them.
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain=domain)
        msg.set_content(m.body)
        context = ssl.create_default_context()
        if url.scheme == "smtps":
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                url.hostname, url.port or 465, timeout=30, context=context
            )
        else:
            server = smtplib.SMTP(url.hostname, url.port or 587, timeout=30)
            server.starttls(context=context)
        with server:
            server.login(mail["MAIL_USER"], mail["MAIL_PASS"])
            # Raises only if every recipient is refused; otherwise it returns the refused.
            refused = server.send_message(msg)
        if refused:
            raise PartialDelivery(f"refused: {', '.join(sorted(refused))}")

    return send


def _when(iso: str | None) -> str:
    """A stored UTC time, in this machine's local time, to the minute."""
    if not iso:
        return "unknown"
    try:
        return dt.datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    except ValueError:
        return iso


def _what(req: dict) -> str:
    days = f"DOY {req['doy']:03d}" if "doy" in req else f"DOY {req['from']:03d}-{req['to']:03d}"
    return f"{req['campaign']} {req['year']} {days}"


@dataclass
class Tally:
    """What a ledger says about one run so far."""

    planned: int = 0
    banked: int = 0
    ok: int = 0
    failed: list[dict] = field(default_factory=list)
    not_run: int = 0

    @property
    def left(self) -> int:
        # run_start's doys include the banked days, which get no attempt_end.
        return max(self.planned - self.banked - self.ok - len(self.failed) - self.not_run, 0)

    def line(self) -> str:
        already = f"{self.banked} already solved, " if self.banked else ""
        return (
            f"Days: {self.ok} solved, {already}{len(self.failed)} failed, "
            f"{self.not_run} not run, {self.left} still to do, of {self.planned} planned"
        )


def tally(entries: list[dict], run: str) -> Tally:
    mine = [e for e in entries if e.get("run") == run]
    start = next((e for e in mine if e.get("event") == "run_start"), {})
    t = Tally(planned=len(start.get("doys", [])), banked=len(start.get("banked", [])))
    latest: dict[int, dict] = {}
    for e in mine:
        if e.get("event") == "attempt_end":
            latest[e["doy"]] = e
    for e in latest.values():
        if e.get("outcome") == "ok":
            t.ok += 1
        elif e.get("outcome") == "failed":
            t.failed.append(e)
        else:
            t.not_run += 1
    t.failed.sort(key=lambda e: e["doy"])
    return t


@dataclass
class Ledgers:
    """Every ledger under SAVEDISK, read once per pass."""

    files: list[tuple[Path, list[dict], float]] = field(default_factory=list)

    @classmethod
    def read(cls, savedisk: Path | None) -> Ledgers:
        out = cls()
        if savedisk is None:
            return out
        for path in sorted(savedisk.glob("*/*/ledger.jsonl")):
            try:
                entries, _ = read_entries(path)
                out.files.append((path, entries, path.stat().st_mtime))
            except OSError:
                continue
        return out

    def for_request(self, req_id: str) -> tuple[list[dict], str, float] | None:
        """The newest run a request started: its ledger's entries, run id, and mtime."""
        for _path, entries, mtime in self.files:
            for e in reversed(entries):
                if e.get("event") == "run_start" and e.get("request") == req_id:
                    return entries, e["run"], mtime
        return None

    def direct_runs(self) -> collections.abc.Iterator[tuple[list[dict], dict, float]]:
        """Runs that didn't come through the queue."""
        for _path, entries, mtime in self.files:
            for e in entries:
                if e.get("event") == "run_start" and "request" not in e and e.get("run"):
                    yield entries, e, mtime


class Notifier:
    def __init__(
        self,
        cfg: Config,
        queue: Queue,
        send: collections.abc.Callable[[Mail], None],
        *,
        now: collections.abc.Callable[[], dt.datetime] = now_utc,
        worker_alive: collections.abc.Callable[[Path], bool] | None = None,
        pid_alive: collections.abc.Callable[[str, int], bool | None] = _pid_alive,
        dry_run: bool = False,
    ) -> None:
        self.cfg = cfg
        self.queue = queue
        self.send = send
        self.now = now
        self.worker_alive = worker_alive or worker_lock_held
        self.pid_alive = pid_alive
        self.dry_run = dry_run
        self.baseline_pass = False
        self.dir = queue.root / "notify"
        self.state_path = self.dir / "state.json"
        self.status_path = self.dir / "status.json"
        self.state: dict = {}
        self.errors: list[str] = []
        self.sent = 0

    # --- state ------------------------------------------------------------------------

    def _load(self) -> bool:
        """True if there was a usable state. A damaged one is kept aside, not trusted."""
        try:
            self.state = json.loads(self.state_path.read_text())
            if isinstance(self.state, dict):
                return True
        except FileNotFoundError:
            pass
        except ValueError:
            if not self.dry_run:
                os.replace(self.state_path, self.state_path.with_suffix(".damaged"))
        self.state = {}
        return False

    def _save(self) -> None:
        if self.dry_run:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.state_path, self.state, tmp_dir=self.dir)

    def _rec(self, section: str, key: str) -> dict:
        return self.state.setdefault(section, {}).setdefault(key, {})

    def _deliver(self, mail: Mail) -> bool:
        """Send, and say whether it went. A failure is recorded and tried next pass;
        a partial delivery counts as gone, because a retry would mail the others again."""
        try:
            self.send(mail)
        except PartialDelivery as exc:
            self.errors.append(f"{mail.subject}: {exc}")
        except Exception as exc:  # noqa: BLE001 -- no mail failure may stop the pass
            self.errors.append(f"{mail.subject}: {type(exc).__name__}: {str(exc)[:200]}")
            return False
        self.sent += 1
        return True

    def _record(self, mail: Mail, rec: dict, **fields: object) -> None:
        """Send, and only if it went, note it in ``rec`` and save at once."""
        if self._deliver(mail):
            rec.update(fields)
            self._save()

    # --- addressing -------------------------------------------------------------------

    def _to(self, *users: str) -> tuple[tuple[str, ...], list[str]]:
        """Addresses for these users plus the maintainer, and who has no address."""
        out = [self.cfg.maintainer]
        missing: list[str] = []
        for user in users:
            address = self.cfg.operators.get(user.upper()) if user else None
            if address:
                if address not in out:
                    out.append(address)
            elif user and user not in missing:
                missing.append(user)
        return tuple(out), missing

    def _link(self, campaign: str, year: int, tail: str = "run") -> str:
        if not self.cfg.console_url:
            return ""
        return f"{self.cfg.console_url}/#/c/{campaign}/{year}/{tail}"

    def _body(self, lines: list[str], missing: list[str]) -> str:
        if missing:
            lines += ["", f"No email address on file for: {', '.join(missing)}."]
        return "\n".join(lines) + "\n"

    # --- the pass ---------------------------------------------------------------------

    def run(self) -> int:
        """One pass, unless the last one is still going. Returns how many problems it had."""
        if self.dry_run:  # it saves nothing, so it can't disturb a real pass
            return self._pass()
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / "lock", "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("bernese-notify: the last pass is still running", file=sys.stderr)
                return 0
            return self._pass()

    def _pass(self) -> int:
        first = not self._load()
        self.baseline_pass = first
        disk = self.cfg.savedisk
        if disk is not None and not disk.is_dir():
            self.errors.append(f"SAVEDISK {disk} isn't a directory, so no ledger can be read")
        ledgers = Ledgers.read(disk)
        if first:
            self._baseline(ledgers)
        else:
            for section in ("finished", "active", "direct"):
                self.state.setdefault(section, {})
            self._finished(ledgers)
            self._active(ledgers)
            self._worker()
            self._halted()
            self._direct(ledgers)
        self._save()
        self._report()
        return len(self.errors)

    def _report(self) -> None:
        if self.dry_run:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            self.status_path,
            {
                "last_pass": self.now().isoformat(),
                "sent": self.sent,
                "errors": self.errors,
                "operators": sorted(self.cfg.operators),
            },
            tmp_dir=self.dir,
        )

    def _baseline(self, ledgers: Ledgers) -> None:
        """First pass: record what already exists, and mail none of it."""
        self.state = {
            "version": 1,
            "since": self.now().timestamp(),
            "finished": {},
            "active": {},
            "direct": {},
        }
        for path in self.queue.done.glob("*.json"):
            self.state["finished"][path.stem] = "baseline"
        now = self.now().isoformat()
        for path in self.queue.active_files():
            self.state["active"][path.stem] = {"started": now, "progress": now}
        for entries, start, _mtime in ledgers.direct_runs():
            self.state["direct"][start["run"]] = {"started": now, "progress": now, "ended": True}
            if self._run_end(entries, start["run"]) is None and self._alive(start):
                self.state["direct"][start["run"]]["ended"] = False

    @staticmethod
    def _run_end(entries: list[dict], run: str) -> dict | None:
        return next(
            (e for e in entries if e.get("event") == "run_end" and e.get("run") == run), None
        )

    def _alive(self, start: dict) -> bool:
        return self.pid_alive(start.get("host", ""), start.get("pid", 0)) is not False

    # --- queued runs ------------------------------------------------------------------

    def _stoppers(self, req_id: str) -> list[str]:
        out = []
        for path in self.queue.done.glob("*.json"):
            try:
                other = read_json(path)
            except (OSError, ValueError):
                continue
            if other.get("kind") == STOP and other.get("applied_to") == req_id:
                out.append(str(other.get("submitted_by", "")))
        return out

    def _finished(self, ledgers: Ledgers) -> None:
        for path in sorted(self.queue.done.glob("*.json")):
            if path.stem in self.state["finished"]:
                continue
            try:
                req = read_json(path)
            except (OSError, ValueError):
                continue
            if req.get("kind") == STOP:
                self.state["finished"][path.stem] = "stop"
                self._save()
                continue
            if self._deliver(self._finished_mail(req, ledgers)):
                self.state["finished"][path.stem] = self.now().isoformat()
                self.state["active"].pop(path.stem, None)
                self._save()

    def _finished_mail(self, req: dict, ledgers: Ledgers) -> Mail:
        outcome = str(req.get("outcome", "unknown"))
        if req.get("kind") not in RUN_KINDS:
            to, _ = self._to()
            return Mail(
                to,
                f"{SUBJECT_PREFIX} A request was {outcome}: {req.get('id')}",
                f"{req.get('detail', '')}\n",
            )
        by = str(req.get("submitted_by", ""))
        stoppers = self._stoppers(str(req["id"]))
        to, missing = self._to(by, *stoppers)
        lines = [
            f"{req['kind']} {_what(req)} ({req.get('pcf')}): {outcome}",
            "",
            f"Started by: {by}",
            f"Started: {_when(req.get('started'))}",
            f"Finished: {_when(req.get('finished'))}",
        ]
        for who in stoppers:
            lines.append(f"Stopped by: {who}")
        found = ledgers.for_request(str(req["id"]))
        failed: list[dict] = []
        if found:
            t = tally(found[0], found[1])
            lines.append(t.line())
            failed = t.failed
        if req.get("detail"):
            lines += ["", str(req["detail"])]
        for e in failed:
            lines += [
                "",
                f"DOY {e['doy']:03d}: {e.get('error', '')}",
                f"  {e.get('note', '')}",
            ]
            link = self._link(req["campaign"], req["year"], f"day/{e['doy']}/failure")
            if link:
                lines.append(f"  {link}")
        link = self._link(req["campaign"], req["year"])
        if link:
            lines += ["", link]
        return Mail(
            to,
            f"{SUBJECT_PREFIX} {_what(req)}: {outcome}",
            self._body(lines, missing),
        )

    def _active(self, ledgers: Ledgers) -> None:
        now = self.now()
        for path in self.queue.active_files():
            try:
                req = read_json(path)
            except (OSError, ValueError):
                continue
            if req.get("kind") not in RUN_KINDS:
                continue
            rid = str(req["id"])
            rec = self._rec("active", rid)
            by = str(req.get("submitted_by", ""))
            to, missing = self._to(by)
            found = ledgers.for_request(rid)
            if "started" not in rec:
                if req["kind"] == PREFLIGHT:
                    rec["started"] = rec["progress"] = now.isoformat()
                else:
                    lines = [
                        f"{req['kind']} {_what(req)} ({req.get('pcf')}) has started.",
                        "",
                        f"Started by: {by}",
                    ]
                    link = self._link(req["campaign"], req["year"])
                    if link:
                        lines += ["", link]
                    mail = Mail(
                        to,
                        f"{SUBJECT_PREFIX} {_what(req)}: started",
                        self._body(lines, missing),
                    )
                    self._record(mail, rec, started=now.isoformat(), progress=now.isoformat())
                continue
            self._progress(req, rec, to, missing, found)
            self._stalled(req, rec, to, missing, found)

    def _progress(
        self,
        req: dict,
        rec: dict,
        to: tuple[str, ...],
        missing: list[str],
        found: tuple[list[dict], str, float] | None,
    ) -> None:
        now = self.now()
        last = dt.datetime.fromisoformat(rec["progress"])
        if (now - last).total_seconds() < self.cfg.progress_hours * 3600:
            return
        lines = [f"{req['kind']} {_what(req)} is still running.", ""]
        if found:
            lines.append(tally(found[0], found[1]).line())
        link = self._link(req["campaign"], req["year"])
        if link:
            lines += ["", link]
        mail = Mail(
            to,
            f"{SUBJECT_PREFIX} {_what(req)}: still running",
            self._body(lines, missing),
        )
        self._record(mail, rec, progress=now.isoformat())

    def _stalled(
        self,
        req: dict,
        rec: dict,
        to: tuple[str, ...],
        missing: list[str],
        found: tuple[list[dict], str, float] | None,
    ) -> None:
        began = req.get("started") or req.get("submitted") or self.now().isoformat()
        since = found[2] if found else dt.datetime.fromisoformat(began).timestamp()
        link = self._link(req["campaign"], req["year"])
        self._stuck(
            rec, to, since, f"{req['kind']} {_what(req)}", f"{_what(req)}: looks stuck",
            missing=missing, tail=["", link] if link else [],
        )  # fmt: skip

    def _stuck(
        self,
        rec: dict,
        to: tuple[str, ...],
        since: float,
        what: str,
        subject: str,
        *,
        missing: list[str] | None = None,
        tail: list[str] | None = None,
    ) -> None:
        """No ledger line for too long. Sent once, and again only if it moved and stuck again."""
        if rec.get("stalled_at") == since:
            return
        idle_min = (self.now().timestamp() - since) / 60
        if idle_min < self.cfg.stall_minutes:
            return
        at = dt.datetime.fromtimestamp(since, dt.UTC).isoformat()
        lines = [
            f"{what} looks stuck: nothing has been recorded for "
            f"{idle_min:.0f} minutes, since {_when(at)}.",
            "",
            "A large day can legitimately take a long time. A person should look.",
            *(tail or []),
        ]
        mail = Mail(to, f"{SUBJECT_PREFIX} {subject}", self._body(lines, missing or []))
        self._record(mail, rec, stalled_at=since)

    # --- the worker -------------------------------------------------------------------

    def _waiting_users(self) -> list[str]:
        users = []
        for path in [*self.queue.active_files(), *self.queue.pending()]:
            try:
                req = read_json(path)
            except (OSError, ValueError):
                continue
            # queue/ can hold anything until the worker rejects it, and it may be down.
            if isinstance(req, dict):
                users.append(str(req.get("submitted_by", "")))
        return users

    def _worker(self) -> None:
        now = self.now()
        rec = self.state.setdefault("worker", {})
        if self.worker_alive(self.queue.root / "worker.lock"):
            rec.clear()
            return
        since = rec.setdefault("down_since", now.isoformat())
        minutes = (now - dt.datetime.fromisoformat(since)).total_seconds() / 60
        if rec.get("sent") or minutes < self.cfg.worker_down_minutes:
            return
        to, missing = self._to(*self._waiting_users())
        lines = [
            "The run worker on gps3 isn't running, so queued runs won't start, "
            "and a run it was supervising has lost its supervisor.",
            "",
            f"Not running since at least {_when(since)}.",
            "A person must look: sudo systemctl status bernese-worker",
        ]
        mail = Mail(
            to, f"{SUBJECT_PREFIX} The run worker is down", self._body(lines, missing)
        )
        self._record(mail, rec, sent=True)

    def _halted(self) -> None:
        path = self.queue.root / "HALTED"
        if not path.exists():
            self.state.pop("halted", None)
            return
        try:
            text = path.read_text()
        except OSError:
            return
        digest = hashlib.sha256(text.encode()).hexdigest()
        if self.state.get("halted") == digest:
            return
        to, missing = self._to(*self._waiting_users())
        mail = Mail(
            to,
            f"{SUBJECT_PREFIX} The run worker has halted",
            self._body(["The worker will claim no new run until this is cleared.", "", text], missing),
        )
        self._record(mail, self.state, halted=digest)

    # --- runs started directly --------------------------------------------------------

    def _direct(self, ledgers: Ledgers) -> None:
        now = self.now()
        to, _ = self._to()
        for entries, start, mtime in ledgers.direct_runs():
            run = start["run"]
            rec = self._rec("direct", run)
            if rec.get("ended"):
                continue
            if "started" not in rec and start.get("ts", 0) < self.state.get("since", 0):
                rec["ended"] = True  # older than this notifier: history, as the baseline treats it
                continue
            what = f"{start.get('campaign')} {start.get('year')}"
            head = f"A run started directly with bernese-run-year: {what}, run {run}."
            if "started" not in rec:
                body = f"{head}\n\nIt went through no queue, so only you are told.\n"
                mail = Mail(to, f"{SUBJECT_PREFIX} {what}: direct run started", body)
                self._record(mail, rec, started=now.isoformat(), progress=now.isoformat())
                continue
            t = tally(entries, run)
            end = self._run_end(entries, run)
            if end is not None:
                halt = end.get("halt")
                outcome = "stopped" if halt else "finished"
                body = f"{head}\n\n{t.line()}\n"
                if halt:
                    body += f"\n{halt}\n"
                for e in t.failed:
                    body += f"\nDOY {e['doy']:03d}: {e.get('error', '')}\n  {e.get('note', '')}\n"
                self._record(
                    Mail(to, f"{SUBJECT_PREFIX} {what}: direct run {outcome}", body), rec, ended=True
                )
                continue
            if not self._alive(start):
                body = f"{head}\n\nIt died without recording an end.\n{t.line()}\n"
                self._record(
                    Mail(to, f"{SUBJECT_PREFIX} {what}: direct run died", body), rec, ended=True
                )
                continue
            self._stuck(
                rec, to, mtime, f"The direct run {what}, run {run},", f"{what}: direct run looks stuck"
            )
            last = dt.datetime.fromisoformat(rec["progress"])
            if (now - last).total_seconds() >= self.cfg.progress_hours * 3600:
                body = f"{head}\n\nStill running.\n{t.line()}\n"
                mail = Mail(to, f"{SUBJECT_PREFIX} {what}: direct run still running", body)
                self._record(mail, rec, progress=now.isoformat())


def worker_lock_held(path: Path, proc_locks: Path = Path("/proc/locks")) -> bool:
    """Whether a process holds an flock on ``path``, read from /proc/locks.

    Taking the lock to test it could make a worker starting at that moment find
    it held and refuse to start. The console's status.flock_held reads it the
    same way; this package can't import that one.
    """
    try:
        st = path.stat()
        want = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
        for line in proc_locks.read_text().splitlines():
            parts = line.split()
            if "FLOCK" in parts and "->" not in parts and want in parts:
                return True
    except OSError:
        pass
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--state", type=Path, default=None, help="the worker's state directory")
    ap.add_argument(
        "--dry-run", action="store_true", help="print what would be sent; send and record nothing"
    )
    ap.add_argument(
        "--test",
        nargs="?",
        const="",
        metavar="INITIALS",
        help="send one test message to the maintainer, and to this operator if named",
    )
    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config)
        send = smtp_sender(cfg.mail)
    except (ConfigError, OSError, tomllib.TOMLDecodeError) as exc:
        print(f"bernese-notify: {exc}", file=sys.stderr)
        return 2
    queue = Queue(args.state or default_state_dir())
    if args.test is not None:
        users = [args.test] if args.test else []
        notifier = Notifier(cfg, queue, send)
        to, missing = notifier._to(*users)
        if missing:
            print(f"bernese-notify: no address on file for {', '.join(missing)}", file=sys.stderr)
            return 2
        try:
            send(Mail(to, f"{SUBJECT_PREFIX} Test message", "If you can read this, run emails reach you.\n"))
        except (OSError, smtplib.SMTPException, PartialDelivery) as exc:
            print(f"bernese-notify: the test message failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(f"sent to {', '.join(to)}")
        return 0
    if args.dry_run:

        def send(m: Mail) -> None:
            print(f"--- to {', '.join(m.to)}\n{m.subject}\n\n{m.body}")

    notifier = Notifier(cfg, queue, send, dry_run=args.dry_run)
    failures = notifier.run()
    if args.dry_run and notifier.baseline_pass:
        print(
            "No state yet, so this is the first pass: it only records what exists and "
            "would mail nothing. A dry run can show messages once a real pass has run."
        )
    for error in notifier.errors:
        print(f"bernese-notify: {error}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
