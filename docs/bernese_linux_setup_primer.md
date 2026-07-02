# Bernese 5.4 on Ubuntu 24.04 — Modern-Toolchain Delta Sheet

You know Bernese and Perl cold — PCFs, BPE, panels, `startBPE`. This doc assumes all of that and
touches none of it. It's the short list of things that broke specifically because of the **2024–2025
Linux toolchain** (GCC 15 / gfortran 15, Ubuntu 24.04, Qt4-vs-g++13+), with exact fixes.

Since you're on Linux by accumulated experience rather than daily driving, the unix-specific tooling
(`objcopy`, `apt`/PPA, shared-library symlinks, container builds) is glossed inline — skip those
asides where they're obvious to you.

Verified end state: EXAMPLE RNX2SNX clean (47 steps), SINEX vs AIUB reference 0.000–0.09 mm; full
71-station national campaign processed the same way.

---

## 1. gfortran ≥ 10 rejects the legacy F77

Modern gfortran defaults to `-fno-allow-argument-mismatch`; the old argument-type mismatches that were
legal pre-F90 are now hard compile errors. AIUB's last *tested* Linux compiler is gfortran 6.4, so
anything on a current distro hits this.

**Fix:** add `-fallow-argument-mismatch` to `FFLAGS` in `$EXE/Makefile.template`, recompile.

(`$F_VERS=GNU` is just the flag-block selector as always — nothing to change there.)

---

## 2. x86-64 ISA note crashes every binary on pre-Haswell hardware

This one is nasty and silent. conda-forge `gfortran` (15.2.0) embeds a `.note.gnu.property` ELF note
demanding **x86-64-v3**. On anything older than Haswell (e.g. a Sandy/Ivy Bridge field laptop = v2),
all ~88 compiled binaries abort at startup with `CPU ISA level is lower than required` — *after* a
clean compile, so it looks like a runtime/env problem, not a build one.

**Fix** (safe — the emitted code is actually baseline; only the note lies). `objcopy` edits a compiled
binary in place; `.note.gnu.property` is a metadata ELF section the kernel/loader reads, *not* code —
stripping it removes the false ISA demand without touching the machine instructions:
```bash
for f in $(find $EXE -maxdepth 1 -type f -executable); do
  objcopy --remove-section=.note.gnu.property "$f"
done
```
(`readelf -n <binary>` shows the note if you want to confirm before/after.) Re-run after any recompile. Haswell-or-newer (v3) servers are unaffected — so this bites the cheap
old laptop you'd actually take to the field, not the rack box.

---

## 3. Why conda-forge gfortran at all (the Ubuntu 24.04 PPA trap)

A PPA is a third-party apt repository; `ubuntu-toolchain-r/test` is the common one for newer GCC. Once
it's on the box it bumps the shared `gcc-*-base` package, and apt then refuses to install the
**versioned `gfortran-13`/`-14` from the main repo** (version conflict against the bumped base) — the
`gfortran` metapackage pins a conflicting version too. Rather than unwind the PPA (which can cascade),
the path of least resistance is putting conda-forge gfortran first on `PATH` before `setup.sh` — which
is exactly what drags in gotcha #2. Pick your poison: clean-apt `gfortran-13/14` if the box has no PPA,
conda-forge + objcopy strip if it does.

Same conflict blocks the X11 `-dev` packages (see #5).

---

## 4. Qt 4.8.7 static build on g++-13+

The menu is the real Ubuntu-24.04 time-sink. Distro Qt4 is gone, and the source won't compile against
g++-13+ unmodified. What works:

- Build in a clean `ubuntu:24.04` Docker container (`docker run -it ubuntu:24.04`, install build deps
  inside, compile there, copy the result out) — isolates the build from whatever X11/header versions
  your host has drifted to. The static output runs on the host regardless.
- **Configure:** `-static` (self-contained menu binary, no Qt runtime needed) +
  `-no-webkit -no-script -no-scripttools` (dodges a JavaScriptCore ambiguous-swap break).
- **4 source patches for g++-13+:**
  1. `mkspecs/linux-g++-64/qmake.conf` → add `-std=gnu++98`
  2. `src/corelib/global/qglobal.h` → `Q_FOREACH` control/XOR rewrite
  3. `tools/linguist/linguist/messagemodel.cpp` → unsigned-comparison fix
  4. `src/plugins/accessible/widgets/itemviews.cpp:396` → `static_cast<QItemSelectionModel::SelectionFlags>()`
- **Prefix** `/Qt4.8.7` is baked into qmake → symlink on host: `sudo ln -s $HOME/Qt4.8.7 /Qt4.8.7`.
- Qt4 also hardcodes the ancient X11R6 path: `sudo ln -s /usr/lib/x86_64-linux-gnu /usr/X11R6/lib`.

Output ~261 MB static build.

---

## 5. X11 `-dev` symlink fallback

Background for the occasional-Linux reader: a shared library ships as `libX11.so.6` (the *soname*, what
programs load at runtime), but the linker at *build* time wants the bare `libX11.so` — normally
provided by the `-dev` package as a symlink. When the PPA conflict (#3) blocks those `-dev` packages,
hand-make the symlinks yourself:
```bash
cd /usr/lib/x86_64-linux-gnu
for p in SM:6 ICE:6 Xrender:1 fontconfig:1 freetype:6 Xext:6 X11:6; do
  sudo ln -sf "lib${p%:*}.so.${p#*:}" "lib${p%:*}.so"   # libX11.so -> libX11.so.6
done
```
Clean box with no PPA: just `apt-get install` the `-dev` packages and skip this entirely.

---

## 6. Two things the installer assumes but doesn't provide

Standard stuff for you, listed only so the reproduction script is complete:
- **CRX2RNX** binary → `$EXE` (RXOBV3 dependency).
- **DE421** → build from JPL ASCII (`header.421` first) via `$EXE/ASC2EPH` → `$MODEL/DE421.EPH`,
  check with `TESTEPH`.
- **DATAPOOL ref symlinks**: tarball ships `EXAMPLE.{CRD,VEL,ABB}_REF`; R2S_COP wants the
  non-`_REF` names → symlink in `$DATAPOOL/REF54/`.

---

## 7. Pinned versions (for reproduction)

| Component | What worked | Note |
|---|---|---|
| OS | Ubuntu 24.04 base | |
| gfortran | conda-forge 15.2.0 (PPA box) or apt `gfortran-13/14` (clean box) | #1 flag always; #2 objcopy if PPA path |
| g++/gcc | 14 | g++-12 blocked by GCC-15 PPA on the test box |
| Qt | 4.8.7 static, 4 patches | #4 |
| perl | 5.40.1 | stock BPE modules only |
| runtime | libgfortran.so.5 | **don't apt-upgrade mid-campaign** — pins drift |

---

*One install order caveat worth stating since it's toolchain-driven: compile Fortran (`setup.sh`
option 5) **before** online updates, and apply the objcopy strip (#2) immediately after each compile —
otherwise the updater can pull a recompile that re-emits the ISA note. Everything else is your usual
flow.*
