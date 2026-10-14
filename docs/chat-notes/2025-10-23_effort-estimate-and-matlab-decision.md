# Effort estimate and the MATLAB decision (2025-10-23)

*Condensed from an AI chat. See [README](README.md).*

## The effort estimate, and why it is not kept

The conversation re-estimated section 12.1 of the automation roadmap for a lead
developer working with an AI coding assistant: 18–26 weeks instead of the
roadmap's 47–67. It was a guess with no measurement behind it, and its
benchmark and licence-cost figures were invented, so none of it is carried
forward. What actually took how long is in the git history.

## The MATLAB decision, which held

The question: replace MATLAB in the velocity step with GNU Octave, with
Fortran/C/C++, or with Python?

The answer was Python (NumPy, SciPy, Matplotlib), for reasons that held up:

- `vel_line_v8.m` uses ordinary numerical and plotting operations, with no
  toolbox or Simulink dependency, so almost all of it has direct NumPy
  equivalents.
- Octave would keep a second language beside the Python automation and is
  reached only through subprocess calls.
- Compiled code buys speed the step doesn't need: Bernese, not the velocity
  fit, is the bottleneck.
- Acceptance would be agreement with MATLAB on the same inputs, not plots that
  merely look the same.

**Outcome.** The port is `pogf_geodetic_suite.timeseries.analysis`, which
reproduces `vel_line_v8_newvelduetooffset_v4.m` for 161 of 165 velocity
components to better than 5e-6 mm/yr against PHIVOLCS' own published output
(`docs/SETTLED.md` §2). Porting it also exposed two defects in published
velocities (`docs/project_documentation/velocity_outlier_policy_delta.md`).
