#!/usr/bin/env bash
# install_bsw_build_toolchain.sh — make BSW 5.4 recompilable on this machine.
#
# WHY THIS IS NEEDED
# BSW 5.4 runs fine here — the 30-day LUZON reprocessing completed 30/30 — but
# it **cannot currently be rebuilt**. `$X/SCRIPT/EXE/Makefile.template` (the
# GNU branch, F_VERS=GNU) invokes the compilers by their UNVERSIONED names:
#
#     F77 = gfortran     FC = gfortran     LD = gfortran     CC = cc
#
# and this machine has only the versioned binaries:
#
#     /usr/bin/gfortran-12   /usr/bin/gcc-12   /usr/bin/g++-12
#
# with no unversioned symlinks and no update-alternatives entries. Verified
# 2026-08-12: `gfortran`, `cc` and `g++` all resolve to nothing, in both a
# non-interactive and a login shell.
#
# WHAT BREAKS WITHOUT THIS (nothing today, three things later)
#   1. §25.3 "Updating Your Installation" — AIUB ships bug fixes as source that
#      must be recompiled. Cannot be applied.
#   2. §25.4.2 "Maximum Dimensions" — changing a compile-time limit in
#      SOURCE/LIB/FOR/M_MAXDIM.f90 (MAXSTA, MAXREC, MAXAMB, MAXSAT...) requires
#      a rebuild. Currently impossible. Not a live constraint — MAXSTA=3000 is
#      far above any PH network size — but it is the escape hatch if one is
#      ever hit.
#   3. §25.2.5 "Compilation of Individual Modules and Programs" — any local
#      source patch or debug rebuild.
#
# The running binaries are untouched by this script. This only makes a future
# rebuild possible; it does not rebuild anything.
#
# WHY build-essential AND NOT just symlinks
# `build-essential` pulls the unversioned `gcc`/`g++`/`cc` names properly
# through the distribution's own alternatives mechanism, which survives package
# upgrades. Hand-made symlinks in /usr/local/bin work until something upgrades
# gcc and they point at a removed binary. `gfortran` (the unversioned
# metapackage) does the same for Fortran.
#
# Usage:  sudo scripts/sudo/install_bsw_build_toolchain.sh          # install
#         sudo scripts/sudo/install_bsw_build_toolchain.sh --check  # report only
set -uo pipefail

if [ "$(id -u)" -ne 0 ] && [ "${1:-}" != "--check" ]; then
    echo "ERROR: needs root for the install — run with sudo, or pass --check." >&2
    exit 1
fi

report() {
    echo "=== compiler commands BSW's Makefile.template expects ==="
    local missing=0
    for c in gfortran cc g++ make; do
        if command -v "$c" >/dev/null 2>&1; then
            printf '  %-10s OK   %s\n' "$c" "$(command -v "$c")"
        else
            printf '  %-10s **MISSING**\n' "$c"
            missing=$((missing + 1))
        fi
    done
    echo
    echo "=== versioned binaries actually present ==="
    local found=0
    for f in /usr/bin/gfortran-* /usr/bin/gcc-[0-9]* /usr/bin/g++-[0-9]*; do
        [ -x "$f" ] || continue
        printf '  %s\n' "$f"
        found=1
    done
    [ "$found" -eq 1 ] || echo "  (none)"
    return "$missing"
}

if [ "${1:-}" = "--check" ]; then
    report
    rc=$?
    echo
    if [ "$rc" -eq 0 ]; then
        echo "All present — BSW can be recompiled."
    else
        echo "$rc command(s) missing — a BSW rebuild would fail at the first file."
        echo "Re-run without --check (as root) to install."
    fi
    exit 0
fi

echo "=== BEFORE ==="
report || true

echo
echo "=== installing build-essential and gfortran ==="
# Deliberately NOT running a full 'apt upgrade' — this adds packages only.
apt-get update || { echo "apt-get update failed" >&2; exit 1; }
apt-get install -y build-essential gfortran || {
    echo "ERROR: install failed. Nothing else was changed." >&2
    exit 1
}

echo
echo "=== AFTER ==="
if report; then
    echo
    echo "All four commands now resolve. BSW 5.4 can be recompiled."
    echo
    echo "NOT done by this script, and deliberately so:"
    echo "  * no rebuild was performed — the running binaries are untouched"
    echo "  * verify a rebuild actually works before relying on it, e.g. by"
    echo "    recompiling one program per DOCU52 §25.2.5, NOT the whole tree"
    echo "  * if the compiler version differs from the one used originally"
    echo "    (F_VERS=GNU, built 2026-02-26), a full rebuild may produce"
    echo "    numerically different binaries — re-run the §23.3 EXAMPLE"
    echo "    campaign verification against the *_REF files afterward"
else
    echo
    echo "WARNING: something is still missing above. Do not assume success." >&2
    exit 1
fi
