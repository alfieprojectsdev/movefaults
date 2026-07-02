"""Tests for cpu_config (RH-006 / task L) + clustering var plumbing."""
from __future__ import annotations

import pytest
from bernese_workflow.cpu_config import compute_maxjobs, set_user_cpu_maxjobs
from bernese_workflow.pcf_context import PCFContext

# Verbatim USER.CPU localhost row (+ MSG line that must NOT be touched).
_USER_CPU = (
    '\nLIST_OF_CPUS 5\n'
    '  "localhost" "echo \'<COMMAND> <ARGV> >> <LOG> 2>&1\' | sh &" "FAST" "2" "0" "0"\n'
    '  "local_sh" "<COMMAND> <ARGV> >> <LOG> 2>&1 &" "EXAMPLE" "0" "0" "0"\n'
    'MSG_LIST_OF_CPUS 1  "List of CPUs"\n'
)


# ---------------------------------------------------------------------------
# compute_maxjobs
# ---------------------------------------------------------------------------

def test_maxjobs_tracks_physical_cores():
    assert compute_maxjobs(8) == 8


def test_maxjobs_reserve():
    assert compute_maxjobs(8, reserve_cores=1) == 7


def test_maxjobs_floors_at_one():
    assert compute_maxjobs(1, reserve_cores=4) == 1


def test_maxjobs_ram_capped():
    # 16 cores but only 8 GB / 2 GB-per-job = 4 → RAM wins.
    assert compute_maxjobs(16, ram_gb=8) == 4


def test_maxjobs_cores_win_when_ram_ample():
    assert compute_maxjobs(4, ram_gb=64) == 4


def test_maxjobs_rejects_bad_input():
    with pytest.raises(ValueError):
        compute_maxjobs(0)
    with pytest.raises(ValueError):
        compute_maxjobs(4, ram_per_job_gb=0)


# ---------------------------------------------------------------------------
# set_user_cpu_maxjobs
# ---------------------------------------------------------------------------

def test_set_maxjobs_rewrites_localhost_only():
    out, changed = set_user_cpu_maxjobs(_USER_CPU, 2)  # 2540M = 2 physical cores
    assert changed is True
    assert '"localhost" "echo \'<COMMAND> <ARGV> >> <LOG> 2>&1\' | sh &" "FAST" "2" "0" "0"' in out
    # local_sh (a different CPU) and the MSG line are untouched.
    assert '"local_sh" "<COMMAND> <ARGV> >> <LOG> 2>&1 &" "EXAMPLE" "0" "0" "0"' in out
    assert 'MSG_LIST_OF_CPUS 1  "List of CPUs"' in out


def test_set_maxjobs_changes_the_value():
    base = _USER_CPU.replace('"FAST" "2"', '"FAST" "1"')
    out, changed = set_user_cpu_maxjobs(base, 8)
    assert changed is True
    assert '"FAST" "8" "0" "0"' in out


def test_set_maxjobs_no_localhost_row():
    _, changed = set_user_cpu_maxjobs('LIST_OF_CPUS 0\n', 4)
    assert changed is False


def test_set_maxjobs_rejects_zero():
    with pytest.raises(ValueError):
        set_user_cpu_maxjobs(_USER_CPU, 0)


# ---------------------------------------------------------------------------
# PCFContext clustering fields (RH-006 plumbing)
# ---------------------------------------------------------------------------

def test_pcfcontext_clustering_defaults():
    ctx = PCFContext(v_crdinf="PGN", v_rnxdir="PGN")
    d = ctx.to_dict()
    assert d["v_clu"] == "10"
    assert d["v_clufin"] == "A"


def test_pcfcontext_clustering_overridable():
    ctx = PCFContext(v_crdinf="PGN", v_rnxdir="PGN", v_clu="6", v_clufin="N")
    d = ctx.to_dict()
    assert d["v_clu"] == "6"
    assert d["v_clufin"] == "N"


def test_template_exposes_clustering_vars():
    from pathlib import Path

    tpl = (
        Path(__file__).resolve().parents[1] / "templates" / "basic_processing.pcf.j2"
    ).read_text()
    assert "V_CLUFIN" in tpl and "{{ v_clufin" in tpl  # newly added, templated
    assert "{{ v_clu " in tpl                           # V_CLU no longer hardcoded 10
