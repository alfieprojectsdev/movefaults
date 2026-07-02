# Bernese GNSS Software 5.4 — Dependency Manifest

Consolidated dependency list for installing/running Bernese 5.4 on Ubuntu 24.04 (Linux Mint 22.2 base).
Grounded in the AIUB `README_INSTALL.TXT` (upstream), the verified T420 install, and live version
checks on 2026-06-22.

- **Upstream source of truth:** `temp/BSW54Unx_2024-11-11/README_INSTALL.TXT` + `README_QT.TXT`
- **Resolved working procedure:** memory `bernese_install.md`
- **Qt build script:** `temp/build_qt4.sh`

> Two distinct dependency classes: **build-time** (compilers, Qt headers — needed only to compile the
> 88 Fortran binaries + the menu GUI) and **runtime** (shared libs + interpreters — needed every session).
> A verified install can drop the build-time compilers; only the runtime set must persist.

---

## 1. Upstream requirements (AIUB README_INSTALL.TXT)

| Requirement | AIUB spec |
|---|---|
| Qt libraries | **Qt 4** (must be **4.8.7**, compiled from source — see `README_QT.TXT`) |
| Perl | **Perl 5** |
| Fortran | **Fortran 2003 compiler** |
| Disk | ≥ 4 GB full install |
| Env | `$QTDIR` must point at the Qt 4 libs **before** running `setup.sh` |

**AIUB tested Fortran compilers (Linux):** `GNU Fortran (GCC) 6.4.0` and `5.4.0`, `pgfortran 18.4`, `NAG 6.2`.
T420 uses **gfortran-14** — far newer than tested → required the argument-mismatch workaround (§4).

---

## 2. Runtime dependencies (must persist — verified live 2026-06-22)

| Dependency | Version on T420 | Role |
|---|---|---|
| `perl` | **5.40.1** | BPE orchestration (`startBPE.pm`, `RUNBPE.pm`, `rnx2snx_pcs.pl`) |
| `libgfortran.so.5` | present `/lib/x86_64-linux-gnu/` | Fortran runtime for the 88 EXE_GNU binaries |
| `make` | GNU Make 4.4.1 | (build-time, but listed; not needed at runtime) |
| `tar`, `gzip`/`gunzip` | system | unpack IGS/RINEX products, `.gz` reference solutions |
| Qt 4.8.7 runtime | static-linked into `menu` (mostly) | GUI; some Qt/X11 `.so` resolved via manual symlinks (§4) |
| X11 display | `DISPLAY` set | required for `menu` GUI |

**Do NOT `apt upgrade` before/during training** — a newer `libgfortran`/Qt could break a verified install.

---

## 3. Build-time dependencies (compile only — may be absent post-install)

| Package | T420 choice | Why this exact package |
|---|---|---|
| Fortran compiler | **gfortran-14** | NOT metapackage `gfortran` (pins gfortran-13, conflicts with GCC 15 PPA on T420) |
| C compiler | **gcc-14** | same PPA-conflict reason |
| C++ compiler | **g++-14** | g++-12 blocked by GCC 15 PPA / gcc-12-base conflict on T420 |
| Qt 4.8.7 | built from source via `temp/build_qt4.sh` | AIUB requires exactly 4.8.7; distro Qt4 unavailable on 24.04 |
| make, tar, gzip | system | build + unpack |
| Perl 5 + standard modules | system | install scripts |

> On 2026-06-22 `gfortran-14`/`gcc-14`/`g++-14` were **not on PATH** — confirming they're build-time only.
> The binaries are already compiled; only `libgfortran.so.5` runtime is needed. Reinstall the compilers
> only if recompiling (e.g. new BPE programs).

`$F_VERS=GNU` (selector string in `LOADGPS.setvar`, not a version) → `Makefile.template` picks the GNU
flag block. Fixed at install; orchestrator never touches it.

---

## 4. T420-specific fixes (build-time) — NOT needed on R740

These were required because the T420 is Sandy Bridge (x86-64-v2) and the apt/PPA state blocked clean
`-dev` packages. **R740 (Haswell, x86-64-v3, clean apt) should not need them.**

1. **ISA mismatch** — conda-forge gfortran 15.2.0 embedded `.note.gnu.property` requiring x86-64-v3;
   T420 is v2 → SIGILL. Fix: `objcopy --remove-section=.note.gnu.property` on all 88 `$EXE/*` binaries.
2. **gfortran ≥ 10 argument mismatch** — add `-fallow-argument-mismatch` to `FFLAGS` in
   `$EXE/Makefile.template` (old F77 type mismatches became hard errors in gfortran 10+).
3. **7 manual Qt/X11 `.so` symlinks** — PPA blocked `-dev` packages; symlink runtime `.so`s for the menu.
4. **Qt build patches (3)** in `build_qt4.sh`: mkspecs `gnu++98` flag, `qglobal.h` `Q_FOREACH` rewrite
   (g++≥9), `messagemodel.cpp` unsigned comparison (g++≥11). Build uses `-static`.
5. **g++-14 instead of g++-12** for the Qt build (PPA conflict).

---

## 5. Data/model files (not packages, but install prerequisites)

| File | Location | Note |
|---|---|---|
| `CRX2RNX` | `$EXE` (`SCRIPT/EXE`) | Hatanaka decompression; required for BPE step RXOBV3 |
| `DE421.EPH` | `$MODEL` (`GLOBAL/MODEL/`) | JPL ephemeris; generated from ASCII via `ASC2EPH` |
| DATAPOOL REF54 symlinks | `$DATAPOOL/REF54/` | `EXAMPLE.CRD/VEL/ABB → *_REF` (R2S_COP expects names without `_REF`) |
| AIUB license | `$X/LICENSE.txt` | institution-level, perpetual, all machines (no per-host activation) |

---

## 6. R740 deployment deltas (BRN-001, pending)

Same OS (Ubuntu 24.04.3), clean apt, Haswell (x86-64-v3). Expected:
- Install **gfortran-14 / gcc-14 / g++-14** (or whatever clean apt provides without PPA conflict).
- Build Qt 4.8.7 via `build_qt4.sh` (patches may still apply — depends on g++ version).
- **Skip** ISA `objcopy` patch (no v2/v3 mismatch).
- Verify `-fallow-argument-mismatch` if gfortran ≥ 10.
- Re-run EXAMPLE verification: `perl $U/SCRIPT/rnx2snx_pcs.pl 2023 0100`, diff `SOL/FIN_20230100.SNX`
  vs `$SAVEDISK/RNX2SNX/2023/SOL/FIN_20230100.SNX.gz_REF` → expect ≤ 0.09 mm.

---

## 7. Python-side (orchestrator + velocity pipeline, separate from Bernese core)

Managed by `uv` in the monorepo, not by Bernese:
- Python 3.11+ (3.13 live)
- `jinja2` (PCF templating in `bernese_workflow.orchestrator`)
- subprocess → invokes Perl `rnx2snx_pcs.pl` and Python `RUNX_v2.py`

See `pyproject.toml` and `docs/project_documentation/pogf_infrastructure/tech_spec_bernese_workflow.md`.
