"""
Pure logic of scripts/local_ci.py: which SHAs get tested, how output is
summarised, and when the heartbeat counts as stale. The side-effecting half
(git, uv, gh) is exercised by running it; see the PR that added it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "local_ci", Path(__file__).resolve().parents[1] / "local_ci.py"
)
ci = importlib.util.module_from_spec(_spec)
sys.modules["local_ci"] = ci  # dataclasses resolve their module by name
_spec.loader.exec_module(ci)

T = ci.Target


def test_untested_shas_are_picked_main_first():
    targets = [T("a" * 40, "main"), T("b" * 40, "#1"), T("c" * 40, "#2")]
    assert ci.select_targets(targets, {}, limit=2) == targets[:2]


def test_tested_shas_are_skipped_whatever_the_result():
    targets = [T("a" * 40, "main"), T("b" * 40, "#1")]
    state = {"a" * 40: {"state": "failure"}, "b" * 40: {"state": "success"}}
    assert ci.select_targets(targets, state, limit=5) == []


def test_harness_errors_retry_but_not_forever():
    t = [T("a" * 40, "main")]
    assert ci.select_targets(t, {"a" * 40: {"state": "error", "attempts": 1}}, 5) == t
    capped = {"a" * 40: {"state": "error", "attempts": ci.MAX_ERROR_ATTEMPTS}}
    assert ci.select_targets(t, capped, 5) == []


def test_a_sha_shared_by_main_and_a_pr_is_tested_once():
    sha = "a" * 40
    picked = ci.select_targets([T(sha, "main"), T(sha, "#7")], {}, limit=5)
    assert picked == [T(sha, "main")]


def test_pytest_summary_takes_the_final_tally():
    out = "....\n==== 2 failed, 834 passed, 6 skipped in 301.20s (0:05:01) ===="
    assert ci.summarize_pytest(out) == "2 failed, 834 passed, 6 skipped"
    assert ci.summarize_pytest("no tally here") == ""


def test_pytest_summary_reads_the_quiet_mode_tally():
    # -q prints the tally without the ==== rule. Missing this is how the first
    # real run posted "pytest FAILED" with no counts.
    out = ".....F.....\n1 failed, 835 passed in 76.13s (0:01:16)\n"
    assert ci.summarize_pytest(out) == "1 failed, 835 passed"


def test_vitest_summary_ignores_colour_codes():
    out = "\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m253 passed\x1b[39m\x1b[22m\x1b[90m (253)\x1b[39m\n"
    assert ci.summarize_vitest(out) == "253 passed"


def test_description_fits_githubs_limit_and_names_the_failure():
    steps = [
        ci.StepResult("pytest", False, "1 failed, 835 passed", 300.0),
        ci.StepResult("vitest", True, "253 passed", 20.0),
    ] * 10
    d = ci.describe(ci.Outcome("failure", steps))
    assert len(d) <= 140
    assert d.startswith("pytest FAILED (1 failed, 835 passed)")


def test_harness_error_is_not_described_as_a_code_failure():
    d = ci.describe(ci.Outcome("error", reason="field_ops imports from /elsewhere"))
    assert d.startswith("harness error:")


def test_heartbeat_age():
    assert ci.heartbeat_age(None, 100.0) is None
    assert ci.heartbeat_age({"at": 40.0}, 100.0) == 60.0


# --- preflight: assert the environment rather than counting skips -----------------


def test_preflight_passes_when_everything_resolves():
    assert ci.preflight(which=lambda t: f"/bin/{t}", can_connect=lambda h, p: True) == []


def test_preflight_names_what_is_missing():
    missing = {"teqc"}
    problems = ci.preflight(
        which=lambda t: None if t in missing else f"/bin/{t}", can_connect=lambda h, p: False
    )
    assert "teqc not on PATH" in problems
    assert any("Postgres not answering" in p for p in problems)


def test_preflight_covers_every_tool_the_tests_check():
    # PREFLIGHT_TOOLS is a hand-carried list. This keeps it honest: every tool
    # name a test file passes to shutil.which must be in it, or a new tool dependency
    # would skip unnoticed on a runner that lacks it, which is the 2026-09-25
    # cron bug (teqc not on cron's PATH, showing only as "1 skipped").
    import re

    root = Path(__file__).resolve().parents[2]
    found = set()
    for path in root.rglob("*.py"):
        parts = set(path.parts)
        if ".venv" in parts or "node_modules" in parts:
            continue
        if "tests" not in parts and path.name != "conftest.py":
            continue
        if path.resolve() == Path(__file__).resolve():
            continue  # this file names the pattern it scans for
        found |= set(re.findall(r'shutil\.which\("([^"]+)"\)', path.read_text(errors="ignore")))
    assert found, "found no shutil.which() calls at all; the scan itself is broken"
    missing = found - set(ci.PREFLIGHT_TOOLS)
    assert not missing, f"tests check for {sorted(missing)}; add them to PREFLIGHT_TOOLS"


def test_skip_reasons_reach_the_description():
    out = (
        "SKIPPED [1] services/x/tests/test_a.py:156: neither teqc nor gfzrnx on PATH\n"
        "SKIPPED [2] tools/y/tests/test_b.py:9: production catalog not present\n"
        "SKIPPED [1] services/x/tests/test_a.py:200: neither teqc nor gfzrnx on PATH\n"
        "830 passed, 4 skipped in 70.00s\n"
    )
    assert ci.skip_reasons(out) == [
        "neither teqc nor gfzrnx on PATH",
        "production catalog not present",
    ]
    s = ci.summarize_pytest_with_skips(out)
    assert s.startswith("830 passed, 4 skipped [skipped: ")
    assert "production catalog not present" in s


def test_preflight_checks_where_the_tests_will_connect():
    # Same variable conftest reads, or preflight could pass on localhost while
    # the DB tests connect elsewhere and skip (review of #254).
    env = {"FIELD_OPS_TEST_DATABASE_URL": "postgresql+asyncpg://u:p@db.example:6543/x"}
    assert ci.pg_test_address(env) == ("db.example", 6543)
    assert ci.pg_test_address({}) == ("localhost", 5433)


def test_ruff_total_sums_the_statistics():
    out = "   20\tE741\tambiguous-variable-name\n    5\tF401\t[*] unused-import\n"
    assert ci.ruff_total(out) == 25
    assert ci.ruff_total("") == 0
    assert ci.ruff_total("error: TOML parse error") is None


# --- fairness: FIFO by when a SHA arrived ------------------------------------------


def test_main_first_then_prs_in_arrival_order():
    targets = [T("m" * 40, "main"), T("n" * 40, "#254"), T("o" * 40, "#249")]
    first_seen = {"m" * 40: 50, "n" * 40: 300, "o" * 40: 100}  # #249's SHA arrived first
    picked = ci.select_targets(targets, {}, limit=2, first_seen=first_seen)
    assert [t.label for t in picked] == ["main", "#249"]


def test_a_new_push_goes_to_the_back_and_cannot_hold_the_slot():
    # The 2026-09-25 starvation: repeated pushes to one PR kept another waiting.
    # Each push is a new SHA with a new arrival time, so it queues behind the
    # waiting one instead of jumping ahead of it.
    waiting = T("w" * 40, "#249")
    busy_v1, busy_v2 = T("a" * 40, "#254"), T("b" * 40, "#254")
    seen = ci.record_first_seen({}, [waiting, busy_v1], now=100)
    seen = ci.record_first_seen(seen, [waiting, busy_v2], now=200)  # push to #254
    picked = ci.select_targets([busy_v2, waiting], {}, limit=1, first_seen=seen)
    assert picked == [waiting]


def test_first_seen_keeps_the_original_time_and_forgets_dead_shas():
    t1, t2 = T("a" * 40, "#1"), T("b" * 40, "#2")
    seen = ci.record_first_seen({}, [t1, t2], now=100)
    seen = ci.record_first_seen(seen, [t1], now=500)
    assert seen == {"a" * 40: 100}


def test_ties_in_arrival_go_to_the_older_pr():
    # Every SHA new in the same tick shares a timestamp. Without a tie-break the
    # stable sort keeps gh's newest-first order, the behaviour FIFO replaces.
    targets = [T("n" * 40, "#257"), T("o" * 40, "#249"), T("p" * 40, "#1000")]
    seen = ci.record_first_seen({}, targets, now=100)
    picked = ci.select_targets(targets, {}, limit=3, first_seen=seen)
    assert [t.label for t in picked] == ["#249", "#257", "#1000"]
