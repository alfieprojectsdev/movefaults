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
