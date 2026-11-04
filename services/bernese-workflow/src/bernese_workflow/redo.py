"""Redo one day: move all of its archived results aside, and put them back if
the new attempt fails.

WHY ALL OF THEM
Deleting a day's FIN files is not a redo on 5.4. A day has seven archived
results; a redo that replaces two leaves five stale ones beside them, and the
next combination picks them up by name. So the whole set moves, as one step,
to <year dir>/SUPERSEDED/<YYYYMMDD-HHMM>/, keeping each file's folder.

THE MANIFEST
Before anything moves, SUPERSEDED/<stamp>/MANIFEST_<yyyy><ddd><s>.json records
every file's path (relative to the year directory), size and sha256. Its
``state`` follows the redo:

  moving          written before the first move
  moved           every file is in SUPERSEDED and verified there
  succeeded       the new attempt banked the day; the old set stays aside
  restored        the attempt failed; its files were removed, the old set is back
  restore-failed  the old set could not be verified; nothing more was touched

Each state change is an atomic rewrite, and ``history`` keeps every state with
its time. Recovery after a crash reads the state and calls ``restore``, which
is written to work from ``moving`` as well as ``moved``: an original that never
moved is recognised by its checksum and left where it is.

The worker calls these under the BPE lock. Nothing here takes it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .month_driver import session_for
from .run_queue import _fsync_dir, now_utc, read_json, write_json_atomic

MANIFEST_VERSION = 1

# (folder, prefix, extension, what): the day's archived results in the year
# directory (V_RESULT for the year). This is bsw-console's RESULT_KINDS plus
# RED_*.SNX, which R2S also archives. Each may be plain or .gz.
RESULT_KINDS: tuple[tuple[str, str, str, str], ...] = (
    ("OUT", "R2S_", ".PRC", "BPE processing summary"),
    ("STA", "FIN_", ".CRD", "Final coordinates"),
    ("SOL", "FIN_", ".SNX", "SINEX, one-session solution"),
    ("SOL", "FIN_", ".NQ0", "Normal equations, final"),
    ("SOL", "RED_", ".SNX", "SINEX, reduced"),
    ("SOL", "RED_", ".NQ0", "Normal equations, reduced"),
    ("ATM", "FIN_", ".TRO", "Troposphere, SINEX format"),
    ("ATM", "FIN_", ".TRP", "Troposphere, Bernese format"),
)

MOVING, MOVED, SUCCEEDED, RESTORED, RESTORE_FAILED = (
    "moving",
    "moved",
    "succeeded",
    "restored",
    "restore-failed",
)


class RestoreFailed(RuntimeError):
    """The old set cannot be put back without guessing. A person must look."""


def day_result_paths(year: int, doy: int, session_char: str = "0") -> list[str]:
    """Every name, relative to the year directory, a day's results can have.

    The .done marker month_driver writes is included: it moves with the set, so
    a restore brings back a banked day and not a FIN run_year would re-run.
    """
    stamp = f"{year}{session_for(doy, session_char)}"
    out = []
    for folder, prefix, ext, _ in RESULT_KINDS:
        name = f"{folder}/{prefix}{stamp}{ext}"
        out += [name, name + ".gz"]
    out.append(f"SOL/FIN_{stamp}.done")
    return out


def present_results(year_dir: Path, year: int, doy: int, session_char: str = "0") -> list[str]:
    return [r for r in day_result_paths(year, doy, session_char) if (year_dir / r).is_file()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _move(src: Path, dst: Path) -> None:
    """rename, which is atomic and keeps the file's bytes and mtime; both
    directories are fsynced so the move survives a power loss."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.rename(src, dst)
    _fsync_dir(dst.parent)
    _fsync_dir(src.parent)


@dataclass
class Manifest:
    """A redo's record, at ``path``. ``data`` is the JSON written there."""

    path: Path
    data: dict

    @property
    def year_dir(self) -> Path:
        return Path(self.data["year_dir"])

    @property
    def aside(self) -> Path:
        return self.path.parent

    @property
    def state(self) -> str:
        return self.data["state"]

    @property
    def files(self) -> list[dict]:
        return self.data["files"]

    def set_state(self, state: str, **fields: object) -> None:
        self.data["state"] = state
        self.data.update(fields)
        self.data.setdefault("history", []).append({"state": state, "at": now_utc().isoformat()})
        write_json_atomic(self.path, self.data)

    @classmethod
    def load(cls, path: Path) -> Manifest:
        return cls(path, read_json(path))


def manifest_path(
    year_dir: Path, year: int, doy: int, session_char: str = "0", at: dt.datetime | None = None
) -> Path:
    """Where this redo's manifest will be: SUPERSEDED/<YYYYMMDD-HHMM>/MANIFEST_<day>.json.

    Local time, the form the console's redo preview shows. Two redos in one
    minute share a directory harmlessly unless they are the same day, which
    gets -2, -3, ... instead.
    """
    stamp = (at or dt.datetime.now()).strftime("%Y%m%d-%H%M")
    name = f"MANIFEST_{year}{session_for(doy, session_char)}.json"
    base = year_dir / "SUPERSEDED"
    candidate, n = base / stamp, 1
    while (candidate / name).exists():
        n += 1
        candidate = base / f"{stamp}-{n}"
    return candidate / name


def move_aside(
    year_dir: Path,
    year: int,
    doy: int,
    mpath: Path,
    *,
    session_char: str = "0",
    request: str = "",
) -> Manifest:
    """Write the manifest, then move every result of the day under its directory.

    If a move fails, the files already moved are moved back (the manifest is left
    at state ``moving`` with an ``error``, and ``restore`` is what puts them back),
    and the error is raised.
    """
    files = present_results(year_dir, year, doy, session_char)
    if not files:
        raise ValueError(f"DOY {doy:03d} has no results in {year_dir} to move aside")
    m = Manifest(
        mpath,
        {
            "v": MANIFEST_VERSION,
            "request": request,
            "year_dir": str(year_dir),
            "year": year,
            "doy": doy,
            "session": session_for(doy, session_char),
            "files": [
                {"path": r, "size": (year_dir / r).stat().st_size, "sha256": sha256(year_dir / r)}
                for r in files
            ],
        },
    )
    mpath.parent.mkdir(parents=True, exist_ok=True)
    m.set_state(MOVING)
    try:
        for f in m.files:
            dst = m.aside / f["path"]
            _move(year_dir / f["path"], dst)
            if sha256(dst) != f["sha256"]:
                raise OSError(f"{f['path']} changed while it was being moved aside")
    except BaseException as exc:
        m.data["error"] = f"{type(exc).__name__}: {exc}"
        restore(m)
        raise
    m.set_state(MOVED)
    return m


def restore(m: Manifest) -> list[str]:
    """Remove what the failed attempt wrote and put the old set back.

    Works from ``moving`` and ``moved``, so it is also the crash recovery. Order:

    1. every file that is in SUPERSEDED is checked against the manifest, and
       every one that is not must be at its original place with its original
       checksum (it never moved). Any mismatch: state ``restore-failed``,
       RestoreFailed raised, nothing touched.
    2. every result file of the day at its original place is deleted, except an
       original that never moved.
    3. each old file is moved back and checked again where it landed.

    Returns the relative paths of the files the attempt wrote and this deleted.

    Any other error part way through (an OSError from a rename or an unlink)
    leaves the day half put back, which is no less a case for a person than a
    checksum mismatch: it is recorded ``restore-failed`` and raised as
    RestoreFailed, so the worker halts instead of recording a plain failure.
    """
    try:
        return _restore(m)
    except RestoreFailed:
        raise
    except Exception as exc:
        why = f"restore stopped part way: {type(exc).__name__}: {exc}"
        try:
            m.set_state(RESTORE_FAILED, problems=[why])
        except Exception:  # noqa: BLE001 -- the raise below is what matters
            pass
        raise RestoreFailed(f"{why} (manifest {m.path})") from exc


def _restore(m: Manifest) -> list[str]:
    year_dir = m.year_dir
    aside: dict[str, Path] = {}
    in_place: set[str] = set()
    problems: list[str] = []
    for f in m.files:
        rel, want = f["path"], f["sha256"]
        moved, orig = m.aside / rel, year_dir / rel
        if moved.is_file():
            if sha256(moved) != want:
                problems.append(f"SUPERSEDED copy of {rel} does not match the manifest")
            aside[rel] = moved
        elif orig.is_file() and sha256(orig) == want:
            in_place.add(rel)  # never moved: a crash or a failure mid-move
        else:
            problems.append(f"{rel} is neither in SUPERSEDED nor in place unchanged")
    if problems:
        m.set_state(RESTORE_FAILED, problems=problems)
        raise RestoreFailed("; ".join(problems) + f" (manifest {m.path})")

    removed = []
    for rel in day_result_paths(m.data["year"], m.data["doy"], m.data["session"][3:]):
        p = year_dir / rel
        if rel not in in_place and p.is_file():
            p.unlink()
            removed.append(rel)
    for d in {(year_dir / r).parent for r in removed}:
        _fsync_dir(d)

    for f in m.files:
        rel = f["path"]
        if rel in aside:
            _move(aside[rel], year_dir / rel)
            if sha256(year_dir / rel) != f["sha256"]:
                m.set_state(RESTORE_FAILED, problems=[f"{rel} does not match after moving back"])
                raise RestoreFailed(f"{rel} does not match the manifest after moving back")
    m.set_state(RESTORED, removed=removed)
    return removed
