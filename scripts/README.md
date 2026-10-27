# scripts/

**This directory is the production path today.** Every production Bernese
solution so far was staged, run and checked by scripts here, not by
`services/bernese-workflow`. `CLAUDE.md` ("How components connect") shows how
they chain.

Each script explains itself in its header (a docstring or the leading comment
block). This index is one line per script, grouped by job. It was generated from
those headers on 2026-10-14; when you add a script, add its line here.

Three scripts have tests in `tests/` (`local_ci.py`, `match_rinex_to_site.py`,
`compare_weekly_solutions.py`); `uv run pytest` runs them. The rest are untested.
Privileged scripts live in `sudo/` and are handed over by absolute path, never
pasted between shells (Claude Code has no tty).

## Bernese production runs

| script | what it does |
|---|---|
| `stage_luzon_campaign.sh` | set up a Bernese 5.4 LUZON campaign (RINEX 2 + 3 staging) |
| `stage_national_campaign.sh` | stage the full Philippine network for a year, not one subnetwork |
| `derive_luzon_pcf.py` | derive a LUZON PCF from BSW 5.4's stock `RNX2SNX.PCF`; refuses dangling `WAIT`s |
| `adapt_luzon_pcf.py` | derive a 5.4 LUZON PCF from the PHIVOLCS 5.2 production PCF |
| `provision_gpsuser.py` | provision `$U` from the repo's gold standard (`config/bernese/gpsuser/`) |
| `add_station_to_campaign.py` | add a station to a campaign's reference files |
| `merge_blq.py` | merge ocean-loading blocks into a BLQ file, above `$$ END TABLE` |
| `fetch_igs_products.sh` | download IGS long-name final products for a day range (SWITCH S3 mirror; AIUB FTP is firewalled) |
| `fetch_fiducial_obs.sh` | download RINEX 3 daily observations for the fiducial stations |
| `run_luzon_month.sh` | one month through `LUZON_DLY`, skipping days whose `FIN` exists |
| `run_luzon_year.sh` | a full year in parallel blocks |
| `run_phref_year.sh` | the same for PHREF |
| `run_pagenet_week.sh` | the PAGENET 7-day weekly run, unattended |
| `pagenet_pcs.pl` | parameterised copy of the stock `rnx2snx_pcs.pl` driver |
| `stack_phref_weekly.sh` | stack PHREF dailies into GPS-weekly solutions with ADDNEQ2 |
| `luzon_status.sh` | one-screen status of a LUZON run |
| `verify_phref_year.sh` | full-population check of a finished PHREF or LUZON year |
| `bsw/apply_bsw54_patches.sh`, `bsw/verify_bsw54_patches.sh`, `bsw/rollback_bsw54_patches.sh` | apply, verify, or roll back the 2024-11-11 BSW 5.4 fixes |
| `run_gmf_comparison.sh` | the measurement that settled GEO-002 |

Launch long runs with `setsid nohup`, never as a Claude Code background job
(`docs/SETTLED.md` §2).

## Checking solutions

| script | what it does |
|---|---|
| `coord_repeatability.py` | day-to-day repeatability from a run's `FIN_*.SNX` |
| `network_coherence_scan.py` | coherent multi-station motion that single-station thresholds miss |
| `compare_solutions.sh` | diff of two solution sets after stripping run timestamps; reads plain and compressed files, and exits 2 on an unreadable or empty one |
| `compare_weekly_solutions.py`, `compare_all_weeks.sh` | weekly Helmert comparison against production |
| `atmospheric_anomaly.py` | confirm or eliminate an ionospheric cause for a bad day |
| `plot_series_overlay.py` | overlay ENU series from two or more runs |
| `sinex_to_crd.py` | SINEX solution to Bernese CRD |

## Velocities and modelling

| script | what it does |
|---|---|
| `make_velocity_field.py` | GMT-ready velocity field; withholds sites whose final interval is under a year |
| `compare_velocity_outlier_policy.py` | what changes when outliers are actually excluded |
| `extract_dislocation_results.py` | the dislocation-model results compilation, in committable form |

## Archive, catalog and want-list

| script | what it does |
|---|---|
| `transfer_phivolcs_datapool.py` | copy the DATAPOOL off the file server, sha256 at copy time |
| `verify_archive.sh` | census and fixity check of the legacy archive on gps3 |
| `snapshot_phivolcs_scripts.py` | snapshot PHIVOLCS' production scripts and event catalog off the file server |
| `build_crd_catalog.py` | site code → coordinate index from Bernese CRD files |
| `match_rinex_to_site.py` | attribute RINEX files to sites by header position (stage 3) |
| `stage4_disagreement_report.py` | turn stage-3 matches into a reviewable disagreement report |
| `raw_rinex_counterparts.py` | raw receiver files with no RINEX counterpart |
| `bern52_inventory_to_csv.py` | export `docs/bern52/BERN52 Inventory.xlsx` to CSV |
| `gnss_want_list.py` | what GNSS data is still missing |
| `want_list_diff.py` | which want-list site-years a drive closes |
| `decode_raw_gap.py` | decode raw files that would close an open site-year |
| `fetch_gnss_mail_archives.py` | local mirror of BSWMAIL and IGSMAIL, for diagnosis |

## Field operations

| script | what it does |
|---|---|
| `field_ops_dev.sh` | bring the field-ops stack up locally |
| `extract_network_inventory.py` | site-inventory spreadsheet to two reviewable CSVs |
| `seed_network_inventory.py` | seed `public.stations` and equipment history from those CSVs |
| `seed_stations.py` | seed stations from a YAML file |
| `seed_field_accounts.py` | one field account per staff member |
| `reset_all_field_passwords.sh` | reissue every field password in one pass |

## Repository workflow

Use these instead of the raw `gh`/`git` commands: a swallowed permission denial
looks exactly like success (`CLAUDE.md`, Branching & Merge Policy).

| script | what it does |
|---|---|
| `open_pr.sh` | open (or report) a PR for a branch |
| `gh_pr_create_nopush.sh` | create a PR for a branch already on origin |
| `merge_pr.sh` | merge a PR; requires a `local-ci/gps3` success on its head |
| `gh_retarget.sh` | change a PR's base branch |
| `git_merge_main.sh`, `git_merge_ref.sh` | merge `origin/main` or another ref into the current branch |
| `local_ci.py` | the CI that actually runs while GitHub Actions is locked: cron on gps3, posts `local-ci/gps3` |
| `audit_doc_references.py` | find documentation citing files that no longer exist |
| `gnss_mirror_update.sh` | refresh the PHIVOLCS-held mirror of this repository |

## Machines

| script | what it does |
|---|---|
| `gps3_reach.sh` | from a client: which network situation is gps3 in? |
| `gps3_reconnect.sh`, `gps3_console_triage.sh` | at the R740 console when it is off the network |
| `gps3_evidence.sh` | collect evidence on gps3 once SSH works |
| `gps3_storage_provision.sh`, `gps3_gpsdata_migrate.sh` | carve the PERC volume into LVs; move GPSDATA onto one |
| `raid_enum.sh`, `smartd_setup.sh`, `patrol_check.sh` | PERC H750 members, SMART monitoring, patrol reads |
| `finch_watch.sh` | an outside witness for finch crashes |

## Notes

- `README-status-email.md`: the run-status email.
- `RESUME_pagenet_week.md`: resuming a PAGENET week.
