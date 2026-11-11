"""The run worker's queue: one JSON file per request, in a state directory.

WHY FILES
The console that submits requests and the worker that runs them are separate
processes, and either may restart at any time. A file outlives both, a person
can read it with cat, and it needs no server. See
docs/project_documentation/run_worker_design.md for the whole design.

LAYOUT
  <state>/tmp/      a request is written here, fsynced, then renamed into queue/
  <state>/queue/    pending requests, <id>.json; the sorted names are the order
  <state>/active/   the one request being run
  <state>/done/     finished requests, with the worker's outcome added

Every move between those directories is a rename, and every rewrite goes
through a temporary file and a rename, so a reader sees a whole file or none.

VALIDATION
Nothing that reads a request trusts it: ``validate`` runs when a request is
submitted and again when the worker reads it, because anything that can write
to queue/ can write anything. No field may carry a path.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import os
import re
import secrets
from collections.abc import Iterator
from pathlib import Path

REQUEST_VERSION = 1
DEFAULT_STATE = Path.home() / ".local/state/bernese-workflow/worker"

START, PREFLIGHT, REDO, STOP = "start", "preflight", "redo", "stop-after-current-day"
KINDS = (START, PREFLIGHT, REDO, STOP)
RUN_KINDS = (START, PREFLIGHT, REDO)

_NAME = re.compile(r"[A-Za-z0-9_]+")
_USER = re.compile(r"[A-Za-z0-9._-]{1,64}")
_ID = re.compile(r"\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{8}")
MAXSESS_DEFAULT = 6
# Written by the worker into active/ and done/, never by a submitter. Crash
# recovery trusts "manifest" in an active request to find the files a redo
# moved, so a request that arrives already carrying it must not be run.
WORKER_FIELDS = frozenset(
    {"started", "worker", "manifest", "superseded", "removed", "days", "preflight_day",
     "outcome", "detail", "finished", "applied_to"}
)  # fmt: skip


class InvalidRequest(ValueError):
    """A request the worker will not run. The message says why."""


def default_state_dir() -> Path:
    v = os.environ.get("BERNESE_WORKER_STATE")
    return Path(v) if v else DEFAULT_STATE


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def new_id(at: dt.datetime | None = None) -> str:
    """Submission time in UTC to the microsecond, then 8 random hex digits.

    Sorting ids is sorting by submission time; the random part only breaks ties.
    """
    t = (at or now_utc()).astimezone(dt.UTC)
    return t.strftime("%Y%m%dT%H%M%S.%fZ") + "-" + secrets.token_hex(4)


def _days_in_year(year: int) -> int:
    return 366 if calendar.isleap(year) else 365


def _name(req: dict, key: str) -> str:
    v = req.get(key)
    if not isinstance(v, str) or not _NAME.fullmatch(v):
        raise InvalidRequest(f"{key} must be letters, digits and _ only, got {v!r}")
    return v


def _int(req: dict, key: str, lo: int, hi: int) -> int:
    v = req.get(key)
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise InvalidRequest(f"{key} must be an integer in {lo}..{hi}, got {v!r}")
    return v


def validate(req: object) -> dict:
    """Return the request if the worker may act on it, else raise InvalidRequest."""
    if not isinstance(req, dict):
        raise InvalidRequest("a request is a JSON object")
    kind = req.get("kind")
    if kind not in KINDS:
        raise InvalidRequest(f"kind must be one of {', '.join(KINDS)}, got {kind!r}")
    if not isinstance(req.get("id"), str) or not _ID.fullmatch(req["id"]):
        raise InvalidRequest(f"malformed id {req.get('id')!r}")
    by = req.get("submitted_by")
    if not isinstance(by, str) or not _USER.fullmatch(by):
        raise InvalidRequest(f"submitted_by must be a username, got {by!r}")
    try:
        dt.datetime.fromisoformat(req.get("submitted", ""))
    except (TypeError, ValueError):
        raise InvalidRequest(
            f"submitted must be an ISO time, got {req.get('submitted')!r}"
        ) from None
    owned = sorted(WORKER_FIELDS & req.keys())
    if owned:
        raise InvalidRequest(f"a request may not carry the worker's own fields: {', '.join(owned)}")
    reason = req.get("reason", "")
    if not isinstance(reason, str) or len(reason) > 2000:
        raise InvalidRequest("reason must be text of at most 2000 characters")
    if kind == STOP:
        target = req.get("target")
        if target is not None and (not isinstance(target, str) or not _ID.fullmatch(target)):
            raise InvalidRequest(f"target must be a request id, got {target!r}")
        return req
    _name(req, "campaign")
    prefix = _name(req, "repr_prefix")
    _name(req, "pcf")
    if prefix == req["campaign"]:
        raise InvalidRequest("repr_prefix must differ from the campaign name")
    year = _int(req, "year", 1980, 2100)
    _int(req, "maxsess", 1, 64)
    # bernese-run-year's --allow-header-mismatches, for a comparison campaign that
    # must process the same files as another run. Absent means false.
    if not isinstance(req.get("allow_header_mismatches", False), bool):
        raise InvalidRequest(
            f"allow_header_mismatches must be true or false, got {req['allow_header_mismatches']!r}"
        )
    last = _days_in_year(year)
    if kind == REDO:
        _int(req, "doy", 1, last)
        if not reason.strip():
            raise InvalidRequest("a redo needs a reason: it is kept with the day's record")
    else:
        a, b = _int(req, "from", 1, last), _int(req, "to", 1, last)
        if a > b:
            raise InvalidRequest(f"from ({a}) is after to ({b})")
    return req


def make_request(
    kind: str, submitted_by: str, *, at: dt.datetime | None = None, **fields: object
) -> dict:
    """A new, validated request. ``maxsess`` defaults to 6 for the run kinds."""
    t = at or now_utc()
    req: dict = {
        "v": REQUEST_VERSION,
        "id": new_id(t),
        "kind": kind,
        "submitted": t.isoformat(),
        "submitted_by": submitted_by,
    }
    if kind in RUN_KINDS:
        req["maxsess"] = MAXSESS_DEFAULT
    req.update({k: v for k, v in fields.items() if v is not None})
    return validate(req)


# --- files ------------------------------------------------------------------------------


def _fsync_dir(d: Path) -> None:
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json_atomic(path: Path, data: object, tmp_dir: Path | None = None) -> None:
    """Write, fsync, rename into place, fsync the directory.

    ``tmp_dir`` must be on the same filesystem as ``path``; it defaults to
    ``path``'s own directory.
    """
    tmp_dir = tmp_dir or path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Queue:
    """The state directory's request files."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_state_dir()
        self.tmp = self.root / "tmp"
        self.queue = self.root / "queue"
        self.active = self.root / "active"
        self.done = self.root / "done"

    def ensure(self) -> Queue:
        for d in (self.tmp, self.queue, self.active, self.done):
            d.mkdir(parents=True, exist_ok=True)
        return self

    # submitting

    def submit(self, req: dict) -> Path:
        """Validate, then write to tmp/ and rename into queue/. Returns the path."""
        validate(req)
        self.ensure()
        path = self.queue / f"{req['id']}.json"
        if path.exists() or (self.done / path.name).exists():
            raise InvalidRequest(f"request {req['id']} already exists")
        write_json_atomic(path, req, tmp_dir=self.tmp)
        return path

    # reading

    def pending(self) -> Iterator[Path]:
        """Queued request files in submission order."""
        if self.queue.is_dir():
            yield from sorted(self.queue.glob("*.json"))

    def active_files(self) -> list[Path]:
        return sorted(self.active.glob("*.json")) if self.active.is_dir() else []

    def find(self, req_id: str) -> tuple[str, Path] | None:
        """Where a request is now: queue, active or done."""
        for where, d in (("queue", self.queue), ("active", self.active), ("done", self.done)):
            p = d / f"{req_id}.json"
            if p.exists():
                return where, p
        return None

    # moving

    def claim(self, path: Path) -> Path:
        """queue/ -> active/, by rename. Raises FileNotFoundError if it is gone."""
        dst = self.active / path.name
        os.rename(path, dst)
        _fsync_dir(self.active)
        return dst

    def update_active(self, path: Path, req: dict) -> None:
        write_json_atomic(path, req, tmp_dir=self.tmp)

    def finish(
        self, path: Path, req: dict, outcome: str, detail: str = "", **fields: object
    ) -> Path:
        """Record the outcome and move the request to done/.

        The outcome is written into the file where it is, then the file is
        renamed, so a request in done/ always carries its outcome.
        """
        req = {**req, "outcome": outcome, "detail": detail, "finished": now_utc().isoformat()}
        req.update(fields)
        write_json_atomic(path, req, tmp_dir=self.tmp)
        dst = self.done / path.name
        os.rename(path, dst)
        _fsync_dir(self.done)
        return dst

    def reject(self, path: Path, why: str) -> Path:
        """A file in queue/ that is not a valid request: kept in done/ with the reason.

        The original bytes are kept under .raw so nothing a person wrote is lost.
        """
        raw = path.read_bytes()
        name = path.stem if _ID.fullmatch(path.stem) else new_id()
        (self.done / f"{name}.raw").write_bytes(raw)
        record = {
            "id": name,
            "outcome": "rejected",
            "detail": why,
            "raw": f"{name}.raw",
            "finished": now_utc().isoformat(),
        }
        write_json_atomic(self.done / f"{name}.json", record, tmp_dir=self.tmp)
        path.unlink()
        return self.done / f"{name}.json"

    def clean_tmp(self, older_than_s: float = 3600.0) -> None:
        """Remove what a submitter that died mid-write left in tmp/."""
        if not self.tmp.is_dir():
            return
        cutoff = now_utc().timestamp() - older_than_s
        for p in self.tmp.iterdir():
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink()
            except FileNotFoundError:
                pass
