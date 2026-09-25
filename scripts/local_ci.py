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

    PATH=/home/gps3/bin:/home/gps3/.local/bin:/usr/local/bin:/usr/bin:/bin
    LOCAL_CI_REPO=/home/gps3/repos/movefaults_clean
    */10 * * * * git -C "$LOCAL_CI_REPO" fetch -q origin main && git -C "$LOCAL_CI_REPO" show origin/main:scripts/local_ci.py | python3 - run >> /home/gps3/.local/state/local-ci/cron.log 2>&1

Why it runs main's copy straight out of git, not the file on disk:
- the file on disk is whatever branch the main checkout has out, which changes
  as people work, and can lack the script entirely;
- a PR must not be able to change the CI that judges it. The runner is always
  the reviewed, merged version; a PR that edits this file is tested by main's.
cron's default PATH has neither uv (~/.local/bin) nor teqc and gfzrnx (~/bin).
Without ~/.local/bin every run exits 2; without ~/bin the RINEX validator test
skips on every unattended run. That second one happened (2026-09-25) and
showed only as "1 skipped", which is why the preflight below exists.
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


# Every external tool a test checks for with shutil.which(), plus what the
# harness itself needs. A missing one means THIS RUNNER is misconfigured, and
# the tests guarded by it would skip rather than fail, which reads as green.
# Kept honest by test_preflight_covers_every_tool_the_tests_check, which
# greps the test tree and fails if a which() target is missing here.
PREFLIGHT_TOOLS = ("git", "uv", "gh", "npm", "node", "teqc", "gfzrnx", "gzip", "zcat")


def pg_test_address(environ=os.environ) -> tuple[str, int]:
    """
    Where the field-ops DB tests will connect: FIELD_OPS_TEST_DATABASE_URL when
    set, else conftest's default. Read from the same variable the tests read, so
    the preflight can't check localhost while the tests go elsewhere and skip.
    """
    from urllib.parse import urlsplit

    url = environ.get("FIELD_OPS_TEST_DATABASE_URL")
    if url:
        parts = urlsplit(url)
        return parts.hostname or "localhost", parts.port or 5432
    return "localhost", 5433  # field-ops/tests/conftest.py's default


def preflight(which=shutil.which, can_connect=None) -> list[str]:
    """
    Problems with the runner's environment, empty when it's fit to judge.

    Skips come in three kinds (review of the skip markers, 2026-09-25): a tool
    missing (the runner is misconfigured), data absent (legitimate on a fresh
    clone), and a race (one scan-jobs test). Only the first is a CI bug, and it
    is exactly what this checks, before the suite, so the status says "teqc
    not on PATH" rather than "1 skipped". Failing on skip counts instead would
    flap on the race and stay red wherever data is absent.
    """
    if can_connect is None:
        can_connect = _tcp_ok
    problems = [f"{t} not on PATH" for t in PREFLIGHT_TOOLS if which(t) is None]
    host, port = pg_test_address()
    if not can_connect(host, port):
        problems.append(f"test Postgres not answering at {host}:{port}")
    return problems


def _tcp_ok(host: str, port: int) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


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


_SKIP_REASON = re.compile(r"^SKIPPED \[\d+\] [^:]+:\d+: (.*)$", re.M)


def skip_reasons(output: str) -> list[str]:
    """Distinct skip reasons from `pytest -rs`, in order of first appearance."""
    seen: list[str] = []
    for r in _SKIP_REASON.findall(output):
        r = r.strip()
        if r not in seen:
            seen.append(r)
    return seen


def summarize_pytest_with_skips(output: str) -> str:
    """Tally, plus WHY things skipped: "1 skipped" is a number nobody decodes."""
    tally = summarize_pytest(output)
    reasons = skip_reasons(output)
    if not reasons:
        return tally
    short = "; ".join(r if len(r) <= 40 else r[:37] + "..." for r in reasons)
    return f"{tally} [skipped: {short}]"


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


def _diff_base(sha: str) -> str:
    """Merge-base with main for a PR head; first parent for main itself."""
    # Compare full SHAs: merge-base prints a full one, and a short `sha` would
    # never match it, making the diff a commit against itself (found testing
    # with short SHAs; production passes full ones, but a string compare of
    # SHAs shouldn't depend on that).
    full = sh(["git", "-C", str(WORKTREE), "rev-parse", sha]).stdout.strip()
    base = sh(["git", "-C", str(WORKTREE), "merge-base", "origin/main", sha]).stdout.strip()
    return f"{full}^" if not base or base == full else base


def changed_files(sha: str, *pathspecs: str) -> list[str]:
    r = sh(
        [
            "git",
            "-C",
            str(WORKTREE),
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            _diff_base(sha),
            sha,
            "--",
            *pathspecs,
        ]
    )
    return [f for f in r.stdout.split() if f]


def changed_python_files(sha: str) -> list[str]:
    """
    Python files this commit changes. Only these are linted in the ordinary case.

    The repository as a whole carries several hundred pre-existing ruff findings
    (the count depends on the working tree), so linting everything would make
    every commit red for reasons it did not introduce, and a check that is
    always red is read as noise and then ignored.
    """
    return changed_files(sha, "*.py")


# Files that change what ruff checks. A commit touching one gets a whole-tree
# lint, because a config change is invisible to a changed-.py-files lint: #253
# changed ONLY ruff's config and was reported "ruff ok (no Python changes)"
# with ruff never run (found in review, 2026-09-25).
RUFF_CONFIG_FILES = ("pyproject.toml", "ruff.toml", ".ruff.toml")


def ruff_total(output: str) -> int | None:
    """Sum of the counts in `ruff check --statistics` output; None if unparseable."""
    counts = re.findall(r"^\s*(\d+)\s+\S", output, re.M)
    return sum(int(c) for c in counts) if counts else (0 if output.strip() == "" else None)


def ruff_config_step(sha: str, env: dict, logdir: Path) -> StepResult:
    """
    Lint the whole tree under the NEW config, and compare with the base config.

    Fails only if ruff can't run with the new config (exit 2: a malformed table,
    an unknown rule). A different findings total is reported, not failed: a
    config change may mean to change what gets flagged, and the reviewer judges
    that. It runs IN ADDITION to the changed-files lint, never instead of it,
    because pyproject.toml also holds dependencies and entry points and changes
    with ordinary feature work (review of #254).

    The base config is swapped into the worktree's own pyproject.toml, not
    written elsewhere and passed with --config: ruff resolves relative paths in
    a config (exclude, per-file-ignores) against the config's own directory, so
    a base config in /tmp would resolve them differently and fabricate a delta.
    The head file is restored before returning, whatever happens.
    """
    t0 = time.monotonic()

    def stats() -> subprocess.CompletedProcess:
        return sh(
            ["uv", "run", "--frozen", "ruff", "check", ".", "--statistics"],
            cwd=WORKTREE,
            env=env,
            timeout=600,
        )

    head = stats()
    out = head.stdout + head.stderr
    base_note = ""
    base_cfg = sh(["git", "-C", str(WORKTREE), "show", f"{_diff_base(sha)}:pyproject.toml"])
    if base_cfg.returncode != 0:
        base_note = ", no base config"
    else:
        target = WORKTREE / "pyproject.toml"
        try:
            target.write_text(base_cfg.stdout)
            base = stats()
        finally:
            sh(["git", "-C", str(WORKTREE), "checkout", "--", "pyproject.toml"])
        out += "\n--- base config ---\n" + base.stdout + base.stderr
        base_total = ruff_total(base.stdout) if base.returncode in (0, 1) else None
        base_note = f", base {base_total}" if base_total is not None else ", base config unusable"
    (logdir / "ruff-config.log").write_text(out)
    secs = round(time.monotonic() - t0, 1)
    if head.returncode not in (0, 1):
        return StepResult("ruff-config", False, "config broken: ruff could not run", secs)
    return StepResult(
        "ruff-config", True, f"whole tree {ruff_total(head.stdout)} findings{base_note}", secs
    )


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
    # Both, never one or the other: the changed-files lint FAILS on new
    # findings, the config step REPORTS a whole-tree delta (review of #254).
    lint = [ruff]
    if changed_files(sha, *RUFF_CONFIG_FILES):
        lint.append(ruff_config_step(sha, env, logdir))
    steps = [
        *lint,
        run_step(
            "pytest",
            ["uv", "run", "--frozen", "pytest", "-q", "-rs", "-p", "no:cacheprovider"],
            WORKTREE,
            env,
            logdir,
            summarize_pytest_with_skips,
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
        problems = preflight() if todo else []
        if problems:
            beat["note"] = "preflight failed: " + "; ".join(problems)
            log(beat["note"])
        for t in todo:
            if args.dry_run:
                continue
            logdir = HOME / "logs" / t.sha
            logdir.mkdir(parents=True, exist_ok=True)
            post_status(t.sha, "pending", f"testing on gps3 since {time.strftime('%H:%M')}")
            t0 = time.monotonic()
            try:
                if problems:  # a misconfigured runner must not report green
                    outcome = Outcome("error", reason="preflight: " + "; ".join(problems))
                else:
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
