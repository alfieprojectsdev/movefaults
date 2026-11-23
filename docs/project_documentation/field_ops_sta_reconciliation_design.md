# Field-ops equipment records and Bernese station information

**Status: proposal, 2026-11-05. Stage 1 is built** as
`bernese-check-equipment` (#332, 2026-11-05); the deploy writes its report
for the console. It compares receivers and antennas, not antenna heights:
see *Antenna heights: not checked yet*. It answers one question: is the
field-ops database connected to the BSW console and
`services/bernese-workflow`? Then it proposes a first, read-only step.

## The answer today: no

Checked on `main` at `5e90398`:

- `services/bernese-workflow` and `services/bsw-console` contain no database
  code and no reference to field-ops. They read Bernese's own files (`.STA`,
  `.CRD`, `.BLQ`, `.ATL`, `.ABB`, PCFs, `SAVEDISK` outputs) and the run ledger
  (`ledger.jsonl`). That is all.
- Field-ops keeps its records in Postgres (`field_ops` schema; production is
  hosted, and gps3 has a local instance on 5433 for tests).
- **Nothing writes a `.STA` from the database, and nothing compares the two.**
  Every station-information file Bernese reads (`PHNAT.STA`, `LUZON.STA`, ...)
  is edited by hand. This week's S01R and LORE fixes were hand edits.

Three documents already describe the database as the source for station
information, and none of it is built:

- Migration `fo002` calls `equipment_history` "the authoritative source" for
  the `.STA` inputs (`arp_height_m`, `elevation_cutoff_deg`).
- `field_ops/models.py` calls `equipment_history` "the authoritative ledger for
  Bernese .STA generation", "reconciled from these rows deliberately".
- `field_ops_amend_review_design.md` says `equipment_history` "is reconciled
  from logsheets and never written directly".

**No code reconciles logsheets into `equipment_history`.** The only writer is
`scripts/seed_network_inventory.py`, which loads a spreadsheet export once.
Read "is reconciled" in those documents as "is meant to be".

## What each side holds

| | `.STA` TYPE 002 row | `field_ops.equipment_history` | Logsheet equipment block |
|---|---|---|---|
| Station key | full 16-column name (`PTAG 22006M005`) | `station_code`, 4 characters | `station_code`, 4 characters |
| Validity | FROM/TO to the second; open end written as `2099 12 31` or blank | `date_installed` / `date_removed`, **dates only** | the visit time; "before" is what was found, "after" what was left |
| Receiver | IGS name (`TRIMBLE NETR9`), serial | manufacturer, `model` as written in the sheet | `receiver_model/serial/firmware_before/_after`, free text |
| Antenna | IGS name + radome (`LEIAR20         LEIM`), serial | `antenna_model`, `radome_type` | `antenna_type/part_number/serial_before/_after`, free text |
| Antenna height | eccentricities N/E/U | `arp_height_m`, **NULL for every seeded row** | not on the continuous sheet |
| Rows | one per equipment period | **one per item**: a receiver row and an antenna row are separate | one per visit |

As seeded, `equipment_history` cannot describe history.
`data/network_inventory/equipment.csv` has **117 rows for 117 stations, 0 with
`date_installed`, 0 with `date_removed`, and no serial numbers**. It is a
snapshot of current equipment with no dates attached. Logsheets are the only
dated field record, and only from the PWA's deployment onward.

## Measured: the sheet against `PHNAT.STA`

On gps3 on 2026-11-05, each station's latest TYPE 002 row in
`$D/REF54/PHNAT.STA` was compared with its row in `equipment.csv`.
`PHNAT.STA` has 405 rows for 174 codes, and 103 of those codes are in the sheet.

| | Equal as written | Differ |
|---|---|---|
| Antenna model | 60 of 103 | 43 |
| Receiver | 81 of 103 | 22 |

The differences are of three kinds. These examples come from the first few
differences printed, not from a full classification:

- **Naming only.** The sheet writes `Leica AR20` where the `.STA` writes the
  IGS name `LEIAR20` (ALCO, BOST), and `GRX1200 GNSS` for
  `LEICA GRX1200+GNSS` (BLNA). A normalisation table would remove these.
- **Probably a typo.** BASC: `.STA` `TRM115000.00`, sheet `TRM11500.00`.
- **Different equipment.** ATIM: `.STA` `TRM57971.00`, sheet `AT504GG`. AURA:
  `.STA` NETR9 with `TRM57971.00`, sheet GRX1200 Pro with `TRM41249.00`. BACO:
  `.STA` `TPSCR.G3`, sheet `TRM41249.00`. BLNA: `.STA` `LEIAX1203+GNSS`, sheet
  `TRM57971.00`.

Either side may be wrong in the third kind. The sheet's export date isn't
recorded, and `.STA` rows are only as current as the last hand edit. A wrong
antenna in the `.STA` file means wrong phase-centre corrections. A wrong
antenna in the sheet means a field team carries the wrong part. The
comparison can't say which side is right; only a person can.

## Proposal, stage 1: a read-only reconciliation report

**What it does.** For each station, it compares what the `.STA` file says was
installed with what field-ops says, and lists every disagreement for a person
to resolve. It writes nothing to either side.

**Inputs.**

- A `.STA` file, read with the existing `sta_type002_rows`, the same reader
  `bernese-check-stations` uses.
- An equipment source. Start with the committed `equipment.csv`, which needs no
  database access and is testable anywhere. Then add logsheets as a second
  source, read from the database (see decision 2).
- A **name map** from the free text people write to IGS receiver and antenna
  names (`Leica AR20` → `LEIAR20`). Keep it as a reviewed YAML file the
  processing lead can edit without touching code, like `bpe_errors.yaml`. An
  unmapped name is reported, never guessed.

**Checks.**

1. **Current equipment:** the latest `.STA` row against the sheet's row. Each
   result is one of: equal; equal after the name map; different; present on
   only one side.
2. **Per visit, when logsheets are added:** for each logsheet, the `.STA` row
   valid at the visit time against `*_before`. When `equipment_changed` is
   true, the `.STA` should have a row starting at or soon after the visit
   with the `*_after` equipment; report its absence. This is the check that
   would have flagged a swap before Bernese processed days under the old row.
3. **Station names:** the 4-character code from field-ops against the 16-column
   `.STA` name. Report codes that map to no `.STA` name, and codes that map to
   more than one.

**Where it lives.** A `--equipment` option on `bernese-check-stations`, or a
sibling command. The report is a table on stdout plus JSON for the console.
It never halts a run. The `.STA`-against-RINEX header check already blocks
when it should, and this report is advisory until a person has worked through
its first output.

**Testable without gps3.** Use the committed CSV and the one committed `.STA`
capture, `config/bernese/gpsuser52-luzon/STA/LUZON.STA`. `PHNAT.STA` is on
gps3 only.

## Later stages: each a separate decision

- **Stage 2: reconcile logsheets into `equipment_history`,** the step the
  three documents above describe as existing. It needs an office review step;
  `field_ops_amend_review_design.md` already sets one out. It also has to
  answer the problem `models.py` names: the offline queue can replay a sheet
  days late, so an automatic write could create overlapping validity windows.
- **Stage 3: suggest `.STA` rows from `equipment_history`.** Suggest only,
  never overwrite. The output would be a proposed TYPE 002 row with its FROM
  date, which must pass `bernese-check-stations`, for a person to paste.
  Blockers today:
  - the database has dates, while `.STA` needs times;
  - there are no serials or antenna heights in the seeded data;
  - the `.STA` files are maintained by the processing team, and some are read
    by BSW 5.2 production.

## Antenna heights: not checked yet

Stage 1 compares equipment names. Nothing compares the height Bernese uses
with a field record, so **a wrong antenna height would go unnoticed.** It is
a constant Up bias in every daily solution for that station, with no step in
the series and no residual to flag it. This section keeps what an earlier,
uncommitted note (2026-10-07) found, so it is not measured again.

**Where the `.STA` heights come from.** `PHNAT.STA` and `PHDEN.STA` were
generated by Bernese from RINEX headers; every row's remark reads
`From <RINEX file>`. The `UP / NORTH / EAST` eccentricities are the header's
`ANTENNA: DELTA H/E/N`, which is whatever the receiver was set to write. On
2026-10-07, 63 of `PHNAT.STA`'s 405 TYPE 002 rows had a non-zero height. A
height of 0 can be right (an antenna on a forced-centring plate, with its
reference point at the marker) or a receiver nobody configured, and nothing
tells the two apart.

**MILA and MSBT are 0 m everywhere we can see:** their 2025 RINEX headers,
`PHNAT.STA`, `PHDEN.STA` and our copy of production's `PHIVOLCS.STA` (dated
13-JUL-20). So their +2 to 3 cm Up against production's WK_2375 is not
explained by our `.STA` differing from that copy. It could be explained by
production's current `.STA` differing from it. Ask the processing lead for the
current `PHIVOLCS.STA` before a height check runs, so it compares against what
production uses now.

**The service's own generator writes no heights.** `generate_sta` in
`campaign_builder.py` writes one window per station and `0.0000` for all
three eccentricities. It is not on the production path, but it is what
`services/bernese-workflow` would write for a new campaign.

**What a height check needs, and what blocks it.**

- **Continuous stations:** compare `UP` with `equipment_history.arp_height_m`
  to 1 mm, and report differences over 2 mm. Blocked today: `arp_height_m` is
  NULL for every seeded row, and the continuous logsheet has no height.
- **Campaign stations:** the logsheet is the only record of the height, and
  each session can differ. Logsheets store `rinex_height_m`, computed from the
  slant heights in the frontend (`computeRH` and `ANTENNA_CONSTANTS` in
  `LogSheetForm.tsx`, TypeScript only). A per-session TYPE 002 row would run
  from the session's `utc_start` to `utc_end` with `rinex_height_m` as `UP`.
  No RINEX header can be trusted to carry a campaign height.

**Prior art for stage 3.** AutoBernese (Danish Agency for Climate Data, MIT
licence, `ab/station/sta.py`) builds `.STA` rows from IGS site logs. Its useful
part is the timeline merge: receiver and antenna changes fall on independent
dates, so cut a new TYPE 002 window at every change of either. It writes
format 1.03; ours and production's are 1.01. Its input, site logs, does not
fit: our stations have none.

**Questions this adds, open until the project lead decides:**

- whether the Python height check reads the same antenna constants as the
  frontend (one data file both read) or keeps a second copy with a test that
  the two agree;
- whether TYPE 003 rows should exclude the first day after an equipment
  change, or stay empty as in production;
- `PHNAT.STA` is shared with PHREF, so a height correction there changes
  PHREF's input too: apply corrections to PHDEN only, or to both.

## Decisions needed

Each decision has a recommendation, made 2026-11-05 from the measurements
above. A decision is open until the project lead accepts or changes it.

1. **Which side is the source of truth for equipment, and when.**
   **Recommended:** the `.STA` file stays the truth for processing, and field
   records are the evidence of what is physically on the monument. Neither
   overwrites the other automatically, and a disagreement is a task for a
   person. The database can't be the source of history yet: its 117 seeded
   rows have no dates, serials or antenna heights. The `.STA` file is what
   Bernese used, the processing team maintains it, and 5.2 production reads it.
   With 43 of 103 antennas in disagreement and the wrong side unknown, neither
   side can be trusted to overwrite the other. Revisit stage 3 once the report
   has run with few unexplained disagreements for a while.
2. **Database access from gps3 for logsheets.**
   **Recommended:** a nightly export on gps3, made with a read-only database
   role; the report reads the export file, not the live database. gps3's
   outbound access already times out at times (GitHub, 2026-10-26 and
   2026-11-05), and a check that depends on a hosted database would fail when
   it is needed. The export makes the report work offline and reproducibly,
   and the report shows the export's timestamp, so stale data is visible. The
   read-only role means the export job cannot write to field-ops. The console
   can move to live reads later if that is worth it.
3. **Who owns the name map.**
   **Recommended:** the processing lead owns the map, and the project lead
   owns the tooling, the same split as `bpe_errors.yaml`. Every name the map
   produces must come from IGS `rcvr_ant.tab`. The first draft comes from the
   103-station comparison, so the owner reviews it rather than starting from
   blank. Field staff don't edit it; they keep writing what is on the hardware.
4. **Whether the console shows the report.**
   **Recommended:** yes, after the command-line report has run and its first
   output has been worked through by a person, as a read-only panel on the
   station view. Equipment changes are per station, not per day, so the panel
   doesn't belong on the Day page. It fits the console's read-only stages 1–2.

## Not proposed

- Writing to `.STA` files automatically.
- Writing to the field-ops database from the Bernese side.
- Blocking BPE runs on this report.
