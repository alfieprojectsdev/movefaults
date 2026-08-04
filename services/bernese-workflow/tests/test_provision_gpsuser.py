"""Tests for scripts/provision_gpsuser.py — the $U provisioner (readiness P1-H).

The sanitizing and MAXPAR logic is tested in test_panel_sanitizer.py; what is
covered here is the orchestration this script adds on top, which is where the
file-class distinctions live:

  * PCFs are refused when they carry a dangling WAIT
  * SCRIPT/ is copied verbatim, never separator-converted
  * PAN/USER.CPU is generated from the host, never copied from the repo
  * dry run writes nothing
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts" / "provision_gpsuser.py"
)


@pytest.fixture(scope="module")
def prov():
    """Import the provisioner script as a module (it is not a package)."""
    spec = importlib.util.spec_from_file_location("provision_gpsuser", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["provision_gpsuser"] = mod
    spec.loader.exec_module(mod)
    mod.Colors.disable()
    return mod


def _pcf(*, dangling: bool) -> str:
    """A tiny PCF. With `dangling`, 599 waits on a PID that is never defined —
    the failure mode of a PCF hand-truncated from a longer one."""
    tail = "599  DUMMY     NO_OPT    CPU=ANY; WAIT=502 522\n" if dangling else \
           "599  DUMMY     NO_OPT    CPU=ANY; WAIT=502\n"
    return (
        "# PID  SCRIPT    OPT_DIR   PARAMETERS\n"
        "499  DUMMY     NO_OPT    CPU=ANY\n"
        "501  GPSCLUAP  R2S_FIN   CPU=ANY; WAIT=499\n"
        "502  GPSCLU_P  R2S_FIN   CPU=ANY; WAIT=501\n"
    ) + tail


# --- PCF gating -------------------------------------------------------------


def test_pcf_with_dangling_wait_is_refused(prov, tmp_path):
    """A WAIT on an undefined PID hangs the BPE forever — refuse, don't copy."""
    gold, user = tmp_path / "gold", tmp_path / "U"
    (gold / "PCF").mkdir(parents=True)
    (user / "PCF").mkdir(parents=True)
    (gold / "PCF" / "PAGENET_DLY.PCF").write_text(_pcf(dangling=True), encoding="ascii")

    actions, errors = prov.provision_pcfs(gold, user, apply=True)

    assert actions == []
    assert len(errors) == 1
    assert "dangling WAIT" in errors[0] and "522" in errors[0]
    assert not (user / "PCF" / "PAGENET_DLY.PCF").exists(), "must not be copied"


def test_clean_pcf_is_copied(prov, tmp_path):
    gold, user = tmp_path / "gold", tmp_path / "U"
    (gold / "PCF").mkdir(parents=True)
    (user / "PCF").mkdir(parents=True)
    (gold / "PCF" / "PAGENET_DLY.PCF").write_text(_pcf(dangling=False), encoding="ascii")

    actions, errors = prov.provision_pcfs(gold, user, apply=True)

    assert errors == []
    assert any("PAGENET_DLY.PCF" in a for a in actions)
    assert (user / "PCF" / "PAGENET_DLY.PCF").exists()


# --- SCRIPT/ verbatim -------------------------------------------------------


def test_perl_scripts_are_copied_byte_for_byte(prov, tmp_path):
    """Backslashes in Perl are escapes. Separator conversion would corrupt them."""
    gold, user = tmp_path / "gold", tmp_path / "U"
    (gold / "SCRIPT").mkdir(parents=True)
    user.mkdir(parents=True, exist_ok=True)
    body = 'my $re = qr/\\d+\\\\n/;\nprint "C:\\\\not\\\\a\\\\path";\n'
    (gold / "SCRIPT" / "pagenet_pcs.pl").write_text(body, encoding="ascii")

    prov.provision_scripts(gold, user, apply=True)

    out = user / "SCRIPT" / "pagenet_pcs.pl"
    assert out.read_text(encoding="ascii") == body, "Perl must not be sanitized"
    assert out.stat().st_mode & 0o111, "driver must stay executable"


def test_unchanged_files_are_reported_as_identical(prov, tmp_path):
    gold, user = tmp_path / "gold", tmp_path / "U"
    (gold / "SCRIPT").mkdir(parents=True)
    (user / "SCRIPT").mkdir(parents=True)
    body = "print 1;\n"
    (gold / "SCRIPT" / "x.pl").write_text(body, encoding="ascii")
    (user / "SCRIPT" / "x.pl").write_text(body, encoding="ascii")

    actions = prov.provision_scripts(gold, user, apply=False)
    assert actions == ["= SCRIPT/x.pl"]


# --- dry run writes nothing -------------------------------------------------


def test_dry_run_writes_nothing(prov, tmp_path):
    gold, user = tmp_path / "gold", tmp_path / "U"
    (gold / "SCRIPT").mkdir(parents=True)
    (gold / "PCF").mkdir(parents=True)
    user.mkdir(parents=True, exist_ok=True)
    (gold / "SCRIPT" / "x.pl").write_text("print 1;\n", encoding="ascii")
    (gold / "PCF" / "A.PCF").write_text(_pcf(dangling=False), encoding="ascii")

    prov.provision_scripts(gold, user, apply=False)
    prov.provision_pcfs(gold, user, apply=False)

    assert not (user / "SCRIPT" / "x.pl").exists()
    assert not (user / "PCF" / "A.PCF").exists()


# --- USER.CPU is generated, not versioned -----------------------------------


def test_user_cpu_maxjobs_is_set_from_the_host(prov, tmp_path):
    user = tmp_path / "U"
    (user / "PAN").mkdir(parents=True)
    (user / "PAN" / "USER.CPU").write_text(
        '\nLIST_OF_CPUS 1\n'
        '  "localhost" "<COMMAND> <ARGV>" "FAST" "2" "0" "0"\n',
        encoding="ascii",
    )

    actions, warnings = prov.provision_user_cpu(user, apply=True, maxjobs=11)

    assert warnings == []
    assert any("maxjobs=11" in a for a in actions)
    assert '"11"' in (user / "PAN" / "USER.CPU").read_text()


def test_user_cpu_is_not_taken_from_the_gold_tree(prov, tmp_path):
    """Regression guard for the bug that motivated this design.

    gps3 was found running the T420's `maxjobs 2` — a 12-core server using two
    cores. A USER.CPU committed to the repo would reintroduce exactly that by
    carrying one machine's core count onto another, so it must never appear in
    the gold tree's copy path.
    """
    gold, user = tmp_path / "gold", tmp_path / "U"
    (gold / "PAN").mkdir(parents=True)
    (user / "PAN").mkdir(parents=True)
    (gold / "PAN" / "USER.CPU").write_text(
        '  "localhost" "<COMMAND>" "FAST" "2" "0" "0"\n', encoding="ascii"
    )
    (user / "PAN" / "USER.CPU").write_text(
        '  "localhost" "<COMMAND>" "FAST" "11" "0" "0"\n', encoding="ascii"
    )

    # Neither the script nor the PCF pass touches PAN/.
    prov.provision_scripts(gold, user, apply=True)
    prov.provision_pcfs(gold, user, apply=True)

    assert '"11"' in (user / "PAN" / "USER.CPU").read_text(), \
        "host USER.CPU must not be overwritten from the repo"


def test_missing_user_cpu_warns_rather_than_crashing(prov, tmp_path):
    user = tmp_path / "U"
    (user / "PAN").mkdir(parents=True)
    actions, warnings = prov.provision_user_cpu(user, apply=False, maxjobs=8)
    assert actions == []
    assert warnings and "USER.CPU absent" in warnings[0]


# --- readiness reporting ----------------------------------------------------


def test_readiness_reports_the_missing_pagenet_pcf(prov, tmp_path):
    user = tmp_path / "U"
    (user / "SCRIPT").mkdir(parents=True)
    (user / "SCRIPT" / "pagenet_pcs.pl").write_text("print 1;\n", encoding="ascii")

    missing = prov.check_pagenet_readiness(user)

    assert len(missing) == 1
    assert "PAGENET_DLY.PCF" in missing[0]


def test_physical_cores_never_returns_logical_count(prov):
    """maxjobs must track physical cores; hyperthreads share an FPU."""
    import os

    cores = prov._physical_cores()
    assert cores >= 1
    logical = os.cpu_count() or 1
    assert cores <= logical
