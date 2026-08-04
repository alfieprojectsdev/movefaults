#!/usr/bin/env python3
"""Provision the Bernese user directory ``$U`` from the repo gold standard.

Readiness task P1-H. The gold standard lives at ``config/bernese/gpsuser/`` and
mirrors ``$U``'s layout; this copies it out, sanitizing on the way, so that a
working environment is reproducible from the repo rather than from someone's
memory of which panels they fixed by hand.

Three file classes, handled differently on purpose:

* ``OPT/**/*.INP`` — separator-sanitized (``\\`` to ``/``), and ``ADDNEQ2.INP``
  has ``MAXPAR`` sized from the station count. Panels carrying hazards the
  sanitizer will not silently auto-fix (foreign absolute paths, hardcoded
  session/date literals) abort the run.
* ``SCRIPT/*`` — copied **verbatim**. A backslash in Perl is an escape, not a
  path separator; converting it would corrupt the driver.
* ``PCF/*.PCF`` — checked for dangling ``WAIT`` references before copying. A
  WAIT on an undefined PID makes the BPE block forever, and it is the specific
  way a hand-truncated PCF fails.

``PAN/USER.CPU`` is **generated**, not copied, because ``maxjobs`` must track the
host's physical core count. See ``--maxjobs``.

DRY RUN BY DEFAULT. Nothing is written without ``--apply`` — verified for all
three classes, not merely intended: until 2026-08-04 the OPT panels were written
regardless, because ``provision_opt_dir`` had no dry-run mode to ask for.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "bernese-workflow" / "src"))

from bernese_workflow.cpu_config import (  # noqa: E402
    compute_maxjobs,
    set_user_cpu_maxjobs,
)
from bernese_workflow.panel_sanitizer import (  # noqa: E402
    find_dangling_waits,
    provision_opt_dir,
)

DEFAULT_GOLD = REPO_ROOT / "config" / "bernese" / "gpsuser"

# Assets run_pagenet_week.sh needs in $U before an acceptance test can run.
REQUIRED_FOR_PAGENET = (
    ("SCRIPT/pagenet_pcs.pl", "BPE driver (parameterized rnx2snx_pcs.pl)"),
    ("PCF/PAGENET_DLY.PCF", "daily PCF, modules 1-14 — capture from the T420"),
)


class Colors:
    OK = "\033[32m"
    WARN = "\033[33m"
    ERR = "\033[31m"
    DIM = "\033[2m"
    OFF = "\033[0m"

    @classmethod
    def disable(cls) -> None:
        cls.OK = cls.WARN = cls.ERR = cls.DIM = cls.OFF = ""


def _physical_cores() -> int:
    """Physical cores, not logical CPUs.

    BPE sub-solves are dense normal-equation inversions — FPU-bound, so two
    hyperthreads sharing one FPU give nothing and oversubscription is slower
    than a correct count. ``os.cpu_count()`` returns logical CPUs and would
    double the answer on any hyperthreaded box.
    """
    try:
        out = subprocess.run(
            ["lscpu", "-p=CORE,SOCKET"], capture_output=True, text=True, check=True
        ).stdout
        pairs = {
            line for line in out.splitlines() if line and not line.startswith("#")
        }
        if pairs:
            return len(pairs)
    except (OSError, subprocess.CalledProcessError):
        pass
    logical = os.cpu_count() or 1
    print(
        f"{Colors.WARN}  ! lscpu unavailable; falling back to logical CPU count "
        f"({logical}) halved{Colors.OFF}"
    )
    return max(1, logical // 2)


def _ram_gb() -> float | None:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except OSError:
        pass
    return None


def provision_scripts(gold: Path, user: Path, apply: bool) -> list[str]:
    """Copy SCRIPT/ verbatim. Never separator-converted — Perl escapes."""
    src = gold / "SCRIPT"
    actions: list[str] = []
    if not src.is_dir():
        return actions
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        target = user / "SCRIPT" / path.relative_to(src)
        same = target.exists() and target.read_bytes() == path.read_bytes()
        actions.append(f"{'=' if same else '->'} SCRIPT/{path.relative_to(src)}")
        if apply and not same:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            target.chmod(0o755)
    return actions


def provision_pcfs(gold: Path, user: Path, apply: bool) -> tuple[list[str], list[str]]:
    """Copy PCF/, refusing any with a dangling WAIT.

    A WAIT on an undefined PID does not fail loudly — the BPE waits for a
    process that will never run, forever. It is also exactly how a PCF
    hand-truncated from a longer one fails, which is the likely provenance of
    anything landing here.
    """
    src = gold / "PCF"
    actions: list[str] = []
    errors: list[str] = []
    if not src.is_dir():
        return actions, errors
    for path in sorted(src.glob("*.PCF")):
        text = path.read_text(encoding="ascii", errors="replace")
        dangling = find_dangling_waits(text)
        if dangling:
            detail = ", ".join(f"L{d.line} WAIT={d.pid}" for d in dangling[:5])
            errors.append(f"PCF/{path.name}: dangling WAIT ({detail})")
            continue
        target = user / "PCF" / path.name
        same = target.exists() and target.read_text(errors="replace") == text
        actions.append(f"{'=' if same else '->'} PCF/{path.name}")
        if apply and not same:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return actions, errors


def provision_panels(
    gold: Path, user: Path, apply: bool, stations: int | None
) -> tuple[list[str], list[str], list[str]]:
    """Sanitize and copy OPT/ panels via the tested provisioner.

    Returns ``(actions, warnings, errors)``. Two things here were wrong before
    2026-08-04 and both defeated the guarantees this script advertises:

    * ``strict=apply`` tied hazard checking to the write mode, so the checks were
      OFF in dry run and ON only under ``--apply``. Backwards: a dry run is
      exactly when you want to be told what would be refused.
    * ``provision_opt_dir`` had no dry-run mode at all, so passing ``apply``
      anywhere near it did not stop the writes — the "DRY RUN" banner was false
      for every panel. Dryness is now a parameter (``dry_run``), and strictness
      is unconditional.

    A refusal is returned as an **error**, not a warning. It previously landed in
    the warning list, so a run that provisioned nothing still exited 0 — the same
    swallowed-status failure this project has now hit six times.
    """
    src = gold / "OPT"
    if not src.is_dir() or not any(src.rglob("*")):
        return [], [], []
    try:
        report = provision_opt_dir(
            src, user / "OPT", n_stations=stations, strict=True, dry_run=not apply
        )
    except ValueError as exc:
        return [], [], [str(exc)]
    verb = "->" if apply else "would write"
    actions = [f"{verb} OPT/{p.relative_to(user / 'OPT')}" for p in report.written]
    warnings = [
        f"OPT/{rel}: " + ", ".join(f"L{w.line} {w.kind}" for w in ws)
        for rel, ws in report.warnings.items()
    ]
    return actions, warnings, []


def provision_user_cpu(
    user: Path, apply: bool, maxjobs: int | None
) -> tuple[list[str], list[str]]:
    """Generate PAN/USER.CPU maxjobs from this host, not from the repo.

    Deliberately not versioned: a committed USER.CPU carries whichever machine
    generated it onto every other one. gps3 was found on 2026-08-03 still
    running the T420's ``maxjobs 2`` — a 12-core server using two cores against
    a known 40-minute single-threaded bottleneck.
    """
    target = user / "PAN" / "USER.CPU"
    if not target.exists():
        return [], [
            f"PAN/USER.CPU absent at {target} — Bernese creates it on first "
            "run; provision panels first, then re-run to size maxjobs"
        ]

    if maxjobs is None:
        cores = _physical_cores()
        ram = _ram_gb()
        maxjobs = compute_maxjobs(cores, ram_gb=ram, reserve_cores=1)
        detail = f"{cores} physical cores"
        if ram:
            detail += f", {ram:.0f} GB RAM"
        detail += ", 1 reserved"
    else:
        detail = "explicit --maxjobs"

    text = target.read_text(encoding="ascii", errors="replace")
    new_text, changed = set_user_cpu_maxjobs(text, maxjobs)
    if not changed:
        return [], ["PAN/USER.CPU has no 'localhost' CPU row — cannot set maxjobs"]
    if new_text == text:
        return [f"= PAN/USER.CPU  maxjobs={maxjobs} ({detail})"], []
    if apply:
        backup = target.with_suffix(f".CPU.bak-{os.getpid()}")
        shutil.copy2(target, backup)
        target.write_text(new_text, encoding="ascii")
    return [f"-> PAN/USER.CPU  maxjobs={maxjobs} ({detail})"], []


def check_pagenet_readiness(user: Path) -> list[str]:
    missing = []
    for rel, why in REQUIRED_FOR_PAGENET:
        if not (user / rel).exists():
            missing.append(f"{rel} — {why}")
    return missing


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Provision $U (GPSUSER) from the repo gold standard.",
        epilog="Dry run by default; pass --apply to write.",
    )
    ap.add_argument("--apply", action="store_true", help="actually write to $U")
    ap.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    ap.add_argument(
        "--user",
        type=Path,
        default=Path(os.environ.get("U", Path.home() / "GPSUSER")),
        help="target $U (default: $U env var, else ~/GPSUSER)",
    )
    ap.add_argument(
        "--stations", type=int, default=None, help="station count for ADDNEQ2 MAXPAR"
    )
    ap.add_argument(
        "--maxjobs", type=int, default=None, help="override detected core count"
    )
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    if not args.gold.is_dir():
        print(f"{Colors.ERR}FATAL: gold standard not found: {args.gold}{Colors.OFF}")
        return 1
    if not args.user.is_dir():
        print(f"{Colors.ERR}FATAL: $U not found: {args.user}{Colors.OFF}")
        return 1

    mode = "APPLY" if args.apply else "DRY RUN — nothing will be written"
    print(f"gold : {args.gold}")
    print(f"$U   : {args.user}")
    print(f"mode : {Colors.WARN}{mode}{Colors.OFF}\n")

    all_actions: list[str] = []
    all_errors: list[str] = []
    all_warnings: list[str] = []

    all_actions += provision_scripts(args.gold, args.user, args.apply)
    acts, errs = provision_pcfs(args.gold, args.user, args.apply)
    all_actions += acts
    all_errors += errs
    acts, warns, errs = provision_panels(
        args.gold, args.user, args.apply, args.stations
    )
    all_actions += acts
    all_warnings += warns
    all_errors += errs
    acts, warns = provision_user_cpu(args.user, args.apply, args.maxjobs)
    all_actions += acts
    all_warnings += warns

    if all_actions:
        print("Plan:")
        for a in all_actions:
            colour = Colors.DIM if a.startswith("=") else Colors.OK
            print(f"  {colour}{a}{Colors.OFF}")
    else:
        print(f"{Colors.DIM}  (nothing to provision){Colors.OFF}")

    if all_warnings:
        print(f"\n{Colors.WARN}Warnings:{Colors.OFF}")
        for w in all_warnings:
            print(f"  {Colors.WARN}! {w}{Colors.OFF}")

    if all_errors:
        print(f"\n{Colors.ERR}Refused:{Colors.OFF}")
        for e in all_errors:
            print(f"  {Colors.ERR}x {e}{Colors.OFF}")

    missing = check_pagenet_readiness(args.user)
    print("\nPAGENET acceptance-test readiness:")
    if missing:
        for m in missing:
            print(f"  {Colors.ERR}MISSING {m}{Colors.OFF}")
        print(
            f"\n  {Colors.DIM}See config/bernese/gpsuser/README.md — "
            f"PAGENET_DLY.PCF must be captured from the T420, not re-derived."
            f"{Colors.OFF}"
        )
    else:
        print(f"  {Colors.OK}all required assets present{Colors.OFF}")

    if not args.apply and all_actions:
        print(f"\n{Colors.DIM}Re-run with --apply to write.{Colors.OFF}")

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
