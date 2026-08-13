# External GNSS tool binaries

Neither binary is committed here — teqc is an external download, gfzrnx is
licensed software. This records **where they are, which build works, and the
output quirks that have already cost debugging time.**

| Tool | Path on gps3 | Version | Reads RINEX 3? |
|---|---|---|---|
| teqc | `/home/gps3/teqc/teqc` | 2019Feb25 (final) | **No — refuses on line 1** |
| gfzrnx | `/home/gps3/gfzrnx/gfzrnx_2.2.0_lx64` | 2.2.0 | Yes |

Neither is on `PATH`. `RinexQC` takes explicit paths, or reads `GFZRNX_BIN`.

## Choosing the teqc build

All four Linux x86-64 builds — `Lx86_64s`, `Lx86_64d`, `CentOSLx86_64s`,
`CentOSLx86_64d` — run on Ubuntu 24.04 / glibc 2.39 and produce **byte-identical
QC output** (verified by md5 on the summary file, 2026-08-13). The static
`Lx86_64s` is installed because it carries no glibc dependency to break on an
OS upgrade, not because it behaves differently.

Downloads come from
`https://www.unavco.org/software/data-processing/teqc/development/<name>.zip`.
**One fetch truncated silently** at 655 KB of 1,001 KB and only surfaced as a
corrupt archive — always `unzip -t` before trusting one.

## Two teqc quirks, both of which were live bugs in our code

1. **The summary file is `<base>.<yy>S`,** not `<base>.S`. `ALAB1210.25o`
   produces `ALAB1210.25S`. Code looking for `stem + ".S"` silently falls back
   to stdout, which contains the ASCII sky plot rather than the numbers — so it
   parses successfully and returns nothing useful.

2. **The metrics are columns of a `SUM` row,** not `key : value` pairs:

   ```
         first epoch    last epoch    hrs   dt  #expt  #have   %   mp1   mp2 o/slps
   SUM 25  5  1 00:00 25  5  1 23:59 24.00  30     -   46370  -   0.74  0.49    284
   ```

   Parse from the right: leading epoch fields vary in width, trailing metrics
   do not. `-` means unavailable and must stay `None` rather than becoming 0.

Both existed in `qc/rinex_qc.py` from the beginning and were **invisible while
teqc was not installed** — the module raised on the missing binary long before
either could show itself. Fixed 2026-08-13, with tests pinning real output.

## Documentation

- `teqc_2019Feb25_options.txt` (here) — the binary's own `+help`, 515 lines.
  **Authoritative for the installed build**; `+help` and `-help` are identical.
- `/home/gps3/teqc/doc/UNAVCO_Teqc_Tutorial.pdf` (61 pp) + `.txt` extraction
- `/home/gps3/gfzrnx/gfzrnx_2.0-8219_manual.pdf` — note this is **2.0** docs
  against a **2.2.0** binary; check `-h` before believing a documented flag.

Prefer captured `+help` over the tutorial for option semantics: it came from
the binary actually in use. Same precedence rule as the BSW manual versus the
installed `.HLP` files.
