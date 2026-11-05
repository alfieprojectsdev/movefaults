# Field-ops equipment records and Bernese station information

**Status: proposal, 2026-11-05. Nothing here is built.** It answers one
question: is the field-ops database connected to the BSW console and
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

## Decisions needed

1. **Which side is the source of truth for equipment, and when.** Today the
   `.STA` file is, in practice, whatever the documents say. Stage 1 doesn't
   need this settled. Stage 3 does.
2. **Database access from gps3 for logsheets.** The options are a read-only
   role on the production database, or a periodic export. gps3's outbound
   access to GitHub already times out at times (2026-10-26, 2026-11-05), so a
   check that depends on a hosted database needs to fail visibly when it
   can't connect.
3. **Who owns the name map.** The processing lead is the natural owner, the
   same as `bpe_errors.yaml`.
4. **Whether the console shows the report.** For example, on the station or
   Day page, beside the HELMCHK RMS.

## Not proposed

- Writing to `.STA` files automatically.
- Writing to the field-ops database from the Bernese side.
- Blocking BPE runs on this report.
