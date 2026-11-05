# Implementation maturity

*Measured 2026-11-05 on `b2ff3de`, not estimated. Re-measure when you update
this: on 2026-08-18 three of five rows had drifted from being carried forward
by hand, by 2026-09-22 three had drifted again (`pogf-geodetic-suite`'s tests
had more than doubled, field-ops' frontend had gone from 69 tests to 253),
by 2026-10-14 two more had (`bernese-workflow` 229 → 250, field-ops 102 + 253 →
131 + 273), and by 2026-11-05 four more had (`bernese-workflow` 250 → 609,
`pogf-geodetic-suite` 260 → 292, vadase 51 → 55, ingestion LOC 632 → 634) and
a seventh component, `bsw-console`, had joined `testpaths` (#315).*

*Size is `modules / LOC / test files`, and the definition is exact so the next
measurement is comparable: **modules** = every tracked `.py` under the
component's `src/`, `__init__.py` included; **LOC** = total lines in those
files; **test files** = tracked `test_*.py` under its `tests/`; **Tests** =
`uv run pytest <component>/tests --collect-only -q`. Checked against the
2026-08-18 tree (`33d6f8e`) before use, where it reproduces the old
figures exactly.*

```bash
c=services/field-ops   # any component
git ls-files -- $c/src | grep -c '\.py$'                          # modules
git ls-files -- $c/src | grep '\.py$' | xargs cat | wc -l          # LOC
git ls-files -- $c/tests | grep -c 'test_.*\.py$'                  # test files
uv run pytest $c/tests --collect-only -q | tail -1                # tests
```

| Component | Size | Tests | Status |
|---|---|---|---|
| drive-archaeologist | 25 / 2998 / 15 | 133 | ~60% — Phase 1 scanner works, archive support partial |
| **bernese-workflow** | 24 / 8610 / 22 | 609 | **~60%, not ~10%** — `backends.py` invokes BSW via `startBPE.pm`; campaign builder, PCF context, panel sanitizer, CODSPP QC, RINEX header validator, CPU config, day-level resume driver (`month_driver.py`, #268) and process-group kill on timeout (#271) all implemented. **Production's BPE step runs through it since 2026-11-04** (`bernese-run-year`; see "What actually runs today" above). **BRN-001 done 2026-07-29** — Bernese 5.4 verified on the R740; LUZON reprocessed 30/30 days unattended 2026-08-06 (5m33s/day) *via `scripts/`*, before the service took over production |
| vadase-rt-monitor | 19 / 1387 / 8 | 55 | ~80% — parser, handler, core logic, leaky integrator, `ReceiverMode` state machine (replaced the old one-way integration latch) |
| **pogf-geodetic-suite** | 19 / 3948 / 14 | 292 | ~75% — coordinates, IGS downloader, RINEX QC (teqc-first, gfzrnx fallback), and `timeseries/`: CRD→ENU, segmented velocities **verified against PHIVOLCS' production MATLAB output**, joint step+rate estimation, GMT velocity-field output |
| **field-ops** | 14 / 3420 / 7 | 131 + 273 | ~90% — offline-first logsheet PWA, exercised on a real handset; `/health` refuses a deploy whose database schema is behind (`schema_check.py`, #249, #256). 131 backend tests (5 of them skip without Postgres) plus **273 frontend (vitest)**; with `bsw-console`'s 16 these are the only frontend tests that run — `packages/CORS-dashboard` carries one 2017 React test file that nothing executes. The frontend count is not in `uv run pytest`: see below |
| ingestion-pipeline | 7 / 634 / 3 | 36 | ~30% — architecture defined, not in the production loop |
| velocity-reviewer | 6 / 424 / 0 | 0 | Working web tool, **no tests** and not in `testpaths` |
| bsw-console | 6 / 1719 / 1 | 19 + 16 | Not yet assessed: merged in #315 after the previous measurement. Web console over `bernese-workflow`, stages 1–2 wired and stage 3 stubbed, per the commit that added it (`e53b531`). 19 backend tests plus **16 frontend (vitest)**, which `local_ci.py` runs alongside field-ops'; not in `uv run pytest` |

Two suites are not components and are not in the table: `scripts/tests` (110)
and `analysis/epb_discriminator/tests` (33).

**The maturity that matters is not module count.** `bernese-workflow` was
listed at ~10% for months while carrying 198 tests, and the genuinely
incomplete part was different from what that number implied: the code existed
and was tested, but the month-long runs went through `scripts/`. That changed
on 2026-11-04, when production's BPE step moved to the service (see "What
actually runs today"). Treat "does production use it?" as the real axis.

## Test totals

```bash
# Run all tests -- all nine suites (seven components, scripts/tests and
# analysis/epb_discriminator/tests): 1418 tests on b2ff3de, 2026-11-05,
# measured OFF gps3: 1410 passed / 8 skipped. The eight: five field-ops tests
# need Postgres at localhost:5433, two bernese-workflow tests need gps3's
# DATAPOOL, and one ingestion-pipeline test needs teqc or gfzrnx on PATH.
# Last full run ON gps3 (Postgres on 5433, the real DATAPOOL, teqc):
# 942 passed / 0 skipped on 6f4ae62, 2026-10-14. Off gps3, tests also skip when
# gps3-only files (real panels, the production offsets catalog) or tools
# (teqc/gfzrnx, gzip, zcat) are absent.
# Skips change the split, not the total. Compare the TOTAL, not the passed count.
#
# History: "six suites, 785 / 3" until scripts/tests joined testpaths (#233);
# "seven suites, 836" until analysis/epb_discriminator/tests joined (#266);
# "eight suites, 942" until services/bsw-console/tests joined (#315).
# The per-component counts in the maturity table plus the two non-component
# suites sum to the total (133+609+55+292+131+36+19 + 110 + 33 = 1418); if they
# stop summing, one is stale.
# Suite selection is `testpaths` in pyproject.toml, not discovery, so a new
# suite has to be added there to be run.
uv run pytest
```
