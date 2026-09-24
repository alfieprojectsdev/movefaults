#!/usr/bin/env python3
"""
local_ci.py -- run the test suite on gps3 for every new commit on main and on
open PRs, and post the result to GitHub as a commit status.

WHY THIS EXISTS
GitHub Actions has run nothing on this repository since 2026-04-23: first it
was disabled, then (from 2026-09-24) the account was billing-locked, and every
job since has zero steps (SETTLED.md §6). Every "tests pass" on a PR in that
time was a claim by whichever machine opened it. gps3 is the one machine that
can run all of it: Postgres on 5433 and the real DATAPOOL are here, so the six
tests that skip elsewhere run here too.

WHAT IT DOES, per run (cron, every 10 minutes; see INSTALL below)
  1. Asks GitHub for main's head and every open PR's head.
  2. Skips SHAs it has already tested. Tests at most --limit new ones, main
     first.
  3. For each: checks the SHA out in a dedicated worktree, gives that worktree
     its OWN virtualenv (uv sync), and refuses to go on unless `field_ops`
     imports from the worktree. That check is the whole point of a separate
     venv: the main checkout's editable install makes a worktree's tests import
     the main checkout's code (SETTLED.md §4), which would report the wrong
     commit's result as this one's.
  4. Runs ruff on the Python files the commit changes, the whole pytest suite,
     and the field-ops frontend (npm ci, vitest, tsc).
  5. Posts `local-ci/gps3` as a commit status: pending at the start, then
     success, failure, or error. "error" means the harness broke (checkout,
     sync, the import check), which is not the same thing as the code failing.
  6. Writes a heartbeat. `local_ci.py status` exits 1 when the heartbeat is
     stale, because a CI that silently stopped is the failure this whole thing
     exists to catch.

WHAT IT DELIBERATELY DOES NOT DO
- Run while a Bernese BPE is running. HANDOVER.md: don't compete with a BPE.
  The run is deferred and the heartbeat says so.
- Run anything against the hosted database. The suite uses the local Postgres
  only. Migrations are guarded by /health (PR #249), not by CI.
- Retry a failure. A failed SHA stays failed until a new commit arrives.
  Harness errors are retried, up to MAX_ERROR_ATTEMPTS.

INSTALL (gps3, user crontab; linger is off, so a systemd user timer would not
fire without a login):

    PATH=/home/gps3/.local/bin:/usr/local/bin:/usr/bin:/bin
    LOCAL_CI_REPO=/home/gps3/repos/movefaults_clean
    */10 * * * * git -C "$LOCAL_CI_REPO" fetch -q origin main && git -C "$LOCAL_CI_REPO" show origin/main:scripts/local_ci.py | python3 - run >> /home/gps3/.local/state/local-ci/cron.log 2>&1

Why it runs main's copy straight out of git, not the file on disk:
- the file on disk is whatever branch the main checkout has out, which changes
  as people work, and can lack the script entirely;
- a PR must not be able to change the CI that judges it. The runner is always
  the reviewed, merged version; a PR that edits this file is tested by main's.
cron's default PATH has neither uv (~/.local/bin) nor, on some hosts, gh; without
the PATH line every run exits 2 and the heartbeat goes stale, which `status`
reports.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# LOCAL_CI_REPO is required when run from stdin (the cron form below).
if not os.environ.get("LOCAL_CI_REPO") and not Path(__file__).is_file():
    # Under `python3 -` __file__ is the string '<stdin>', not missing, so
    # deriving REPO from it would silently give the parent of the working
    # directory. Refuse instead. (Measured in review of #251.)
    sys.exit("local_ci.py: LOCAL_CI_REPO must be set when the script is read from stdin")
REPO = Path(os.environ.get("LOCAL_CI_REPO") or Path(__file__).resolve().parents[1])
SLUG = os.environ.get("LOCAL_CI_SLUG", "alfieprojectsdev/movefaults")
HOME = Path(os.environ.get("LOCAL_CI_HOME", Path.home() / ".local/state/local-ci"))
WORKTREE = Path(os.environ.get("LOCAL_CI_WORKTREE", Path.home() / "ci/movefaults-wt"))
CONTEXT = "local-ci/gps3"
MAX_ERROR_ATTEMPTS = 3
STALE_AFTER_S = 30 * 60
BPE_PATTERN = r"startBPE|RUNBPE|_pcs\.pl"
FRONTEND = "services/field-ops/frontend"


# --- pure logic (unit-tested) ----------------------------------------------------


@dataclass(frozen=True)
class Target:
    sha: str
    label: str  # "main" or "#249"


@dataclass
class StepResult:
    name: str
    ok: bool
    summary: str
    seconds: float


@dataclass
class Outcome:
    state: str  # success | failure | error
    steps: list[StepResult] = field(default_factory=list)
    reason: str = ""


def select_targets(targets: list[Target], state: dict, limit: int) -> list[Target]:
    """New SHAs first by position (main is listed first), deduplicated, capped."""
    picked: list[Target] = []
    seen: set[str] = set()
    for t in targets:
        if t.sha in seen:
            continue
        seen.add(t.sha)
        rec = state.get(t.sha)
        if rec is None or (
            rec.get("state") == "error" and rec.get("attempts", 0) < MAX_ERROR_ATTEMPTS
        ):
            picked.append(t)
        if len(picked) >= limit:
            break
    return picked


_PYTEST_TAIL = re.compile(r"^=*\s*((?:\d+ \w+(?:, )?)+) in [\d.]+s", re.M)
_VITEST_TESTS = re.compile(r"^\s*Tests\s+(.*?)\s*(?:\(\d+\))?\s*$", re.M)


def summarize_pytest(output: str) -> str:
    """'836 passed, 0 skipped' style tail line, or '' if none found."""
    matches = list(_PYTEST_TAIL.finditer(output))
    return matches[-1].group(1).strip() if matches else ""


def summarize_vitest(output: str) -> str:
    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    m = _VITEST_TESTS.search(plain)
    return m.group(1).strip() if m else ""


def describe(outcome: Outcome) -> str:
    """Commit-status description; GitHub caps it at 140 characters."""
    if outcome.state == "error":
        text = f"harness error: {outcome.reason}"
    else:
        parts = [
            f"{s.name} {'ok' if s.ok else 'FAILED'}" + (f" ({s.summary})" if s.summary else "")
            for s in outcome.steps
        ]
        text = "; ".join(parts)
    return text if len(text) <= 140 else text[:137] + "..."


def heartbeat_age(heartbeat: dict | None, now: float) -> float | None:
    if not heartbeat or "at" not in heartbeat:
        return None
    return now - float(heartbeat["at"])


# --- side effects ---------------------------------------------------------------------


def sh(
    cmd: list[str], cwd: Path | None = None, timeout: int = 3600, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)


def gh_targets() -> list[Target]:
    main = sh(["gh", "api", f"repos/{SLUG}/commits/main", "--jq", ".sha"], timeout=60)
    if main.returncode != 0:
        raise RuntimeError(f"gh api commits/main failed: {main.stderr.strip()[:200]}")
    targets = [Target(main.stdout.strip(), "main")]
    prs = sh(
        [
            "gh",
            "pr",
            "list",
            "-R",
            SLUG,
            "--state",
            "open",
            "--json",
            "number,headRefOid",
            "--jq",
            '.[]|"\\(.number) \\(.headRefOid)"',
        ],
        timeout=60,
    )
    if prs.returncode != 0:
        raise RuntimeError(f"gh pr list failed: {prs.stderr.strip()[:200]}")
    for line in prs.stdout.strip().splitlines():
        num, sha = line.split()
        targets.append(Target(sha, f"#{num}"))
    return targets


def post_status(sha: str, state: str, description: str) -> bool:
    """Post and READ BACK: a gh write that exits 0 is not proof it landed."""
    r = sh(
        [
            "gh",
            "api",
            "-X",
            "POST",
            f"repos/{SLUG}/statuses/{sha}",
            "-f",
            f"state={state}",
            "-f",
            f"context={CONTEXT}",
            "-f",
            f"description={description}",
        ],
        timeout=60,
    )
    if r.returncode != 0:
        log(f"  status post failed for {sha[:7]}: {r.stderr.strip()[:200]}")
        return False
    back = sh(
        [
            "gh",
            "api",
            f"repos/{SLUG}/commits/{sha}/statuses",
            "--jq",
            f'[.[]|select(.context=="{CONTEXT}")][0].state',
        ],
        timeout=60,
    )
    if back.stdout.strip() != state:
        log(f"  status for {sha[:7]} did not read back as {state!r} (got {back.stdout.strip()!r})")
        return False
    return True


def runner_version() -> str:
    """
    Which local_ci.py is judging, and how fresh that is.

    Cron runs origin/main's copy, and origin/main is only as fresh as the last
    successful fetch. A fetch that silently failed would run an old judge while
    the output looked normal, so every run logs the commit it came from and the
    age of the fetch. (Raised in review of #251.)
    """
    sha = sh(["git", "-C", str(REPO), "rev-parse", "--short", "origin/main"], timeout=30)
    fetch_head = REPO / ".git" / "FETCH_HEAD"
    try:
        age = f"{int((time.time() - fetch_head.stat().st_mtime) // 60)} min"
    except OSError:
        age = "unknown"
    src = "stdin (origin/main)" if not Path(sys.argv[0]).is_file() else sys.argv[0]
    ref = sha.stdout.strip() if sha.returncode == 0 else "REV-PARSE FAILED"
    return f"{src} @ origin/main {ref} in {REPO}, last fetch {age} ago"


def bpe_running() -> bool:
    return sh(["pgrep", "-f", BPE_PATTERN], timeout=10).returncode == 0


def clean_env() -> dict:
    env = {
        k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")
    }
    env["CI"] = "1"
    return env


def prepare_worktree(sha: str) -> str | None:
    """Check `sha` out in WORKTREE. Returns an error string, or None on success."""
    f = sh(["git", "-C", str(REPO), "fetch", "-q", "origin", sha], timeout=600)
    if f.returncode != 0:
        return f"git fetch {sha[:7]}: {f.stderr.strip()[:120]}"
    if not (WORKTREE / ".git").exists():
        WORKTREE.parent.mkdir(parents=True, exist_ok=True)
        r = sh(["git", "-C", str(REPO), "worktree", "add", "--detach", str(WORKTREE), sha])
    else:
        r = sh(["git", "-C", str(WORKTREE), "checkout", "-q", "--detach", "--force", sha])
    if r.returncode != 0:
        return f"checkout: {r.stderr.strip()[:120]}"
    # Keep the venv and node_modules between runs; everything else is reset.
    r = sh(["git", "-C", str(WORKTREE), "clean", "-qfdx", "-e", ".venv", "-e", "node_modules"])
    if r.returncode != 0:
        return f"git clean: {r.stderr.strip()[:120]}"
    head = sh(["git", "-C", str(WORKTREE), "rev-parse", "HEAD"]).stdout.strip()
    if head != sha:
        return f"worktree is at {head[:7]}, not {sha[:7]}"
    return None


def changed_python_files(sha: str) -> list[str]:
    """
    Python files this commit changes: against its merge-base with main for a PR
    head, against its first parent for main itself.

    Only these are linted. The repository as a whole carries several hundred
    pre-existing ruff findings (666 on 2026-09-24), so linting everything would
    make every commit red for reasons it did not introduce, and a check that is
    always red is read as noise and then ignored.
    """
    base = sh(["git", "-C", str(WORKTREE), "merge-base", "origin/main", sha]).stdout.strip()
    if not base or base == sha:
        base = f"{sha}^"
    r = sh(
        [
            "git",
            "-C",
            str(WORKTREE),
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            base,
            sha,
            "--",
            "*.py",
        ]
    )
    return [f for f in r.stdout.split() if f]


def import_check(env: dict) -> str | None:
    """field_ops must import from the worktree, or every result is someone else's."""
    r = sh(
        [
            "uv",
            "run",
            "--frozen",
            "python",
            "-c",
            "import field_ops, pathlib; print(pathlib.Path(field_ops.__file__).resolve())",
        ],
        cwd=WORKTREE,
        env=env,
        timeout=300,
    )
    where = r.stdout.strip()
    if r.returncode != 0 or not where.startswith(str(WORKTREE.resolve())):
        return f"field_ops imports from {where or '?'} (not the worktree)"
    return None


def run_step(
    name: str,
    cmd: list[str],
    cwd: Path,
    env: dict,
    logdir: Path,
    summarize=lambda out: "",
    timeout: int = 3600,
) -> StepResult:
    t0 = time.monotonic()
    try:
        r = sh(cmd, cwd=cwd, env=env, timeout=timeout)
        out, ok = r.stdout + r.stderr, r.returncode == 0
    except subprocess.TimeoutExpired as e:
        out, ok = f"TIMEOUT after {timeout}s\n{e.stdout or ''}{e.stderr or ''}", False
    (logdir / f"{name}.log").write_text(out)
    return StepResult(name, ok, summarize(out), round(time.monotonic() - t0, 1))


def test_sha(sha: str, logdir: Path) -> Outcome:
    err = prepare_worktree(sha)
    if err:
        return Outcome("error", reason=err)
    env = clean_env()
    sync = sh(["uv", "sync", "--all-extras", "--frozen"], cwd=WORKTREE, env=env, timeout=1800)
    (logdir / "uv-sync.log").write_text(sync.stdout + sync.stderr)
    if sync.returncode != 0:
        return Outcome("error", reason="uv sync failed")
    err = import_check(env)
    if err:
        return Outcome("error", reason=err)

    fe = WORKTREE / FRONTEND
    changed = changed_python_files(sha)
    if changed:
        ruff = run_step(
            "ruff",
            ["uv", "run", "--frozen", "ruff", "check", *changed],
            WORKTREE,
            env,
            logdir,
            lambda out: f"{len(changed)} changed file(s)",
        )
    else:
        ruff = StepResult("ruff", True, "no Python changes", 0.0)
    steps = [
        ruff,
        run_step(
            "pytest",
            ["uv", "run", "--frozen", "pytest", "-q", "-p", "no:cacheprovider"],
            WORKTREE,
            env,
            logdir,
            summarize_pytest,
        ),
    ]
    npm_ci = run_step(
        "npm-ci", ["npm", "ci", "--no-audit", "--no-fund"], fe, env, logdir, timeout=900
    )
    if not npm_ci.ok:
        return Outcome("error", steps, reason="npm ci failed")
    steps += [
        run_step("vitest", ["npm", "test"], fe, env, logdir, summarize_vitest),
        run_step("tsc", ["npx", "tsc", "--noEmit"], fe, env, logdir),
    ]
    return Outcome("success" if all(s.ok for s in steps) else "failure", steps)


# --- state ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}", flush=True)


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    tmp.replace(path)


def cmd_run(args) -> int:
    HOME.mkdir(parents=True, exist_ok=True)
    lock = open(HOME / "lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another run is in progress; exiting")
        return 0

    state = load(HOME / "state.json", {})
    beat = {"at": time.time(), "ran": [], "note": "", "runner": runner_version()}
    log(f"runner: {beat['runner']}")
    try:
        if bpe_running() and not args.ignore_bpe:
            beat["note"] = "deferred: a Bernese BPE is running"
            log(beat["note"])
            return 0
        targets = gh_targets()
        todo = select_targets(targets, state, args.limit)
        log(
            f"{len(targets)} targets, {len(todo)} to test: "
            + ", ".join(f"{t.label}@{t.sha[:7]}" for t in todo)
        )
        for t in todo:
            if args.dry_run:
                continue
            logdir = HOME / "logs" / t.sha
            logdir.mkdir(parents=True, exist_ok=True)
            post_status(t.sha, "pending", f"testing on gps3 since {time.strftime('%H:%M')}")
            t0 = time.monotonic()
            try:
                outcome = test_sha(t.sha, logdir)
            except Exception as e:  # harness bug: report it, never swallow it
                outcome = Outcome("error", reason=f"{type(e).__name__}: {e}"[:120])
            desc = describe(outcome)
            posted = post_status(t.sha, outcome.state, desc)
            prev = state.get(t.sha, {})
            state[t.sha] = {
                "label": t.label,
                "state": outcome.state,
                "description": desc,
                "posted": posted,
                "seconds": round(time.monotonic() - t0),
                "finished": dt.datetime.now().isoformat(timespec="seconds"),
                "attempts": prev.get("attempts", 0) + 1,
            }
            save(HOME / "state.json", state)
            beat["ran"].append(f"{t.label}@{t.sha[:7]}={outcome.state}")
            log(f"  {t.label}@{t.sha[:7]}: {outcome.state} -- {desc}")
        return 0
    except Exception as e:
        beat["note"] = f"run failed: {type(e).__name__}: {e}"[:300]
        log(beat["note"])
        return 1
    finally:
        save(HOME / "heartbeat.json", beat)


def cmd_status(args) -> int:
    beat = load(HOME / "heartbeat.json", None)
    age = heartbeat_age(beat, time.time())
    if age is None:
        print("local-ci: NO HEARTBEAT -- never run, or its state directory is missing")
        return 1
    stale = age > STALE_AFTER_S
    print(
        f"local-ci: last run {int(age // 60)} min ago{'  ** STALE **' if stale else ''}"
        f"  {beat.get('note', '')}"
    )
    print(f"  runner: {beat.get('runner', '?')}")
    for sha, rec in sorted(
        load(HOME / "state.json", {}).items(), key=lambda kv: kv[1].get("finished", "")
    )[-args.last :]:
        print(
            f"  {rec.get('finished', '?')}  {rec.get('label', '?'):>5} {sha[:7]}  "
            f"{rec.get('state'):8} {rec.get('description', '')}"
        )
    return 1 if stale else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="test new SHAs and post statuses")
    r.add_argument("--limit", type=int, default=2)
    r.add_argument("--dry-run", action="store_true", help="list what would be tested")
    r.add_argument("--ignore-bpe", action="store_true")
    s = sub.add_parser("status", help="heartbeat and recent results; exit 1 if stale")
    s.add_argument("--last", type=int, default=10)
    args = p.parse_args(argv)
    if shutil.which("gh") is None or shutil.which("uv") is None:
        print("local-ci needs gh and uv on PATH", file=sys.stderr)
        return 2
    return cmd_run(args) if args.cmd == "run" else cmd_status(args)


if __name__ == "__main__":
    sys.exit(main())
