# CR-20260903 — Stage 3 needs no decoding step

**For:** the gps3 session, following `~/handover/CR-20260902-crd-catalog.md`
**From:** T420, 2026-09-03. Every figure below was measured on gps3 over ssh
and the probe scripts are named so they can be re-run.

---

## The correction

The catalog brief framed stage 3 as **raw → RINEX → header → match**, with the
raw decode as step one. That framing is wrong, and it made stage 3 look blocked
on `runpkr00`.

**The archive already holds 444,085 RINEX observation files against 75,381 raw
ones.** Every sampled RINEX file carries `APPROX POSITION XYZ`. Stage 3 can run
today, on a corpus almost six times larger than the raw one, with no decoding
and no new tooling.

## What was measured

Full walk of `/srv/gnss-archive`, 671,269 files. Sampled with a fixed seed;
header read to `END OF HEADER`, not a fixed line count.

| format | files | carry `APPROX POSITION XYZ` | needs |
|---|---:|---|---|
| `.YYo` plain | 83,471 | **200 / 200** | nothing |
| `.YYo.gz` | 71,789 | **100 / 100** | stdlib `gzip` |
| `.YYo.Z` | 8,185 | **200 / 200** | `zcat` |
| `.YYd.gz` (Hatanaka) | 219,915 | **200 / 200** | stdlib `gzip` |
| `.YYd.Z` (Hatanaka) | 60,285 | **200 / 200** | `zcat` |
| `.YYd` plain | 440 | 35 / 200 — see below | nothing |
| **RINEX observation total** | **444,085** | | |
| raw `.T0x` / `.tgd` / `.mNN` | 75,381 | — | `runpkr00` |

`gunzip`, `uncompress`, `zcat` and `unzip` are all already on gps3.

### CRX2RNX is not required

This is the part worth internalising. A Hatanaka file's **header is plaintext**;
only the observation records are compressed. So `APPROX POSITION XYZ` is
readable from a `.YYd` straight after decompression, and 200/200 confirms it on
both `.gz` and `.Z`. `CRX2RNX` is absent on gps3 and on the T420, and stage 3
does not need it. It would only be needed to read *observations*, which stage 3
does not do.

### The `.YYd` plain anomaly is an extension lying

165 of 200 sampled plain `.YYd` appeared to lack the header. They are not
Hatanaka text at all — they are **`.Z`-compressed files whose `.Z` suffix was
stripped**, carrying the LZW magic `\x1f\x9d`:

```
shao1850.09d  size=315465  first bytes: \x1f\x9d ...
```

**Sniff the magic bytes; do not trust the extension.** `\x1f\x8b` gzip,
`\x1f\x9d` LZW, `PK\x03\x04` zip, otherwise plain text. That one rule turns this
440-file oddity into a non-issue and will also catch the same problem wherever
else in the archive a suffix was lost — likely a FAT copy, since the drives that
fed this archive are vfat and NTFS.

## Where everything is on gps3

```
/srv/gnss-archive/                    671,269 files, the whole archive
  datapool/PHIVOLCS/                  the current production datapool
  legacy/RECOVERED_HD-LBU2_WD20EARS_WCAZA4430660/
  legacy/RECOVERED_SEAGATE_W2A0W9T2_DATA0/        59,953 of the raw files
  legacy/RECOVERED_DOSTB20150918_from_BackupPlus/ 10,323 raw
  legacy/RECOVERED_GPS_1TB_2_WD10EARS_WCAV5M032380/
  processed/luzon-bern52/

docs/bern52/crd_catalog.csv           the stage-2 catalog, in the repo
```

## The three binaries are now on gps3

They were on the T420 only until today; the brief's claim that `runpkr00` is
"genuinely absent" was true of gps3 when written. Now at `~/bin`, verified by
md5 against the T420 copies and confirmed to execute:

```
~/bin/teqc       teqc 2019Feb25                     684c0557f363b8ca90ab3fb645b9c3f7
~/bin/gfzrnx     gfzrnx 2.2.0 lx64                  34ad983c9bb3d656c02f2a8a6139e2a9
~/bin/runpkr00   v5.40, 32-bit static, runs here    1b95b9834806bb25742f5efb1ffb4bf1
```

**`~/bin` is not on the default `PATH`.** Export it, or call by absolute path.

**None of these are needed for stage 3.** They are for the separate raw-decode
work. Two cautions carried over from the T420 session, unchanged:

* `teqc` was discontinued in 2019 and **cannot read RINEX 3 at all** — it
  refuses on line 1. Not a problem here, since stage 3 reads headers directly.
* `gfzrnx`'s free licence covers research use; **operational pipeline use needs
  a commercial licence.** Deciding that is not gps3's call to make silently.

## What stage 3 should do

1. Walk the RINEX observation files, sniffing magic bytes rather than trusting
   suffixes, and read each header to `END OF HEADER`.
2. Take `APPROX POSITION XYZ` and the `MARKER NAME` / `MARKER NUMBER` fields.
3. Match the position against `docs/bern52/crd_catalog.csv` — 2,189 sites.
   Remember what the catalog says about itself: it resolves to about **100 m**,
   it is an identification index and not a coordinate product, and
   `nearest_other_m` already names the pairs no position match can separate.
   **616 sites sit within 100 m of another.** Those need the marker name, or an
   explicit "ambiguous" verdict — not a confident guess.
4. Report agreement and disagreement between the header-derived site and the
   one implied by the directory path. **The disagreements are the product**, not
   a failure: path-derived attribution is inference from how somebody once filed
   a directory, and this is the first evidence that can contradict it.

Do not silently prefer one source over the other. Where they disagree, say so
and show both.

## Separate work, deliberately not in scope here

* **How many of the 75,381 raw files have no RINEX counterpart.** That is the
  number that says whether decoding is worth doing at all, and it is a
  different question from "can stage 3 run" — which is now answered yes.
  Until it is measured, nobody should assume the raw files are either redundant
  or essential.
* The DATA0 raw tree is 59,953 of those files and is where that question will
  mostly be decided.
