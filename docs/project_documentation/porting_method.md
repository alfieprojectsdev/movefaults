# Porting PHIVOLCS' MATLAB analyses: the method

*Written 2026-11-13. Applies to every port out of `analysis/`: the 2-D model
(`velproj_loop.m`, `makeG_2ds_v3_loop.m`), the bootstrap (`bootstrap_v2.py` with
`matlab.engine`), the figures, and the MCMC in `06 Ku-en`.*

The target is no MATLAB dependency, with everything running on gps3
(`SETTLED.md` section 3). The language is open: Python with NumPy by default, and
C or Fortran for a kernel that profiling shows is hot. `modeling/disloc.py` and
`dc3d.py` already compile their C on gps3.

## The order

**1. Collect reference outputs before writing any code.** Run the MATLAB, or
find runs already made, and save the inputs, the outputs and the settings
together. Outputs as printed (tables, text files) are the reference, not
figures. Without them a port can only be checked against itself.

*Precedent:* the velocity port was checked against production's
`Velocity_rover(regress)_10`: 161 of 165 components agree to 5e-6 mm/yr
(`SETTLED.md` section 2). That comparison is what lets staff trust it.

**2. List the defects before porting, and don't fix them yet.** Read the source
and write down what looks wrong, with the line. Port assessment findings 1 to 7
are this list for `analysis/`.

**3. Port faithfully, defects included.** Match the reference to the precision
it was printed at, with a test that loads the saved output and compares. If the
port and the MATLAB disagree, the port is wrong until shown otherwise. A
disagreement found here is cheap; found after a fix it's ambiguous, because you
can't tell the fix from a porting mistake.

**4. Make each fix a named switch, with a delta report.** The default can be the
corrected behaviour or the legacy one, but the other stays one flag away, and
the PR states what the fix changes on real data.

*Precedents:* `--outlier-mode record|exclude`, where `record` reproduces the
published velocities; and `legacy_sigma` in the Leyte reproduction (not yet in the repo), where the
projection σ formula moves Southern Leyte's dip-90° pick rate from 72% to 80%.

**5. Optimise last, behind the parity tests.** Once the tests pin the numbers,
restructure freely. Most speed comes from the method: the bootstrap's Green's
functions don't depend on the resample, so computing them once took an
iteration from about 1.5 h in MATLAB to 0.04 s. Profile before reaching for C
or Fortran; vectorised NumPy is often enough, and a compiled kernel is worth it
only where the profile says so.

## Where a faithful port is impossible

| Case | Example | What to compare instead |
|---|---|---|
| Unseeded randomness | the bootstrap's resampling; the MCMC seeds from the clock | Distributions, not values: run both many times and compare the spread of picks and intervals. The port takes a seed and records it |
| Numerical failure in the original | `metropolis_log.m` multiplies two `exp()` terms and overflows to NaN (finding 7) | Port the intent in log space. Show on cases where the original doesn't overflow that both agree, then report how often the original failed |
| A toolbox or copyrighted function | `lsqlin.m`, `qpsub.m` (MathWorks) | An open solver for the same problem. Compare solutions on the reference inputs, to the solver's tolerance. The MathWorks files never enter the repo |
| Code that can't run as it stands | GUI dialogs (`questdlg`, `inputdlg`), Windows-only imports | Replace the interaction with arguments. Check the computation behind it on a synthetic case with a known answer, or against a second implementation (e.g. `disloc3d.m` against `disloc3d.py`) |

## What every port records

- A seed, where anything is random.
- A manifest beside the outputs: input checksums, the settings, and the code
  version. `velocities_manifest.json` is the pattern.
- Its legacy switches, listed in `--help`.

## What this method is not

It isn't a reimplementation from the algorithm's description, fixing defects
as you go. That route is faster to write, but nothing can check it, and any
difference from the published results is unexplained. Staff can't adopt a
result that differs from theirs for reasons nobody can name.
