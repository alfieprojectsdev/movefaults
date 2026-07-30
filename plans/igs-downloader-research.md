# IGS-001: IGS Downloader Rewrite — Research Notes

**Date:** 2026-04-29
**Status:** Research complete. Implementation pending (next session).
**Ticket:** IGS-001 in `docs/project_documentation/ticket_backlog.md`

---

## Problem Statement

The existing `packages/pogf-geodetic-suite/src/pogf_geodetic_suite/igs_downloader.py`
constructs download URLs using pre-2022 short-name conventions (`cod{week}{dow}.sp3.Z`)
that have not existed on any IGS server since GPS week 2238 (27 November 2022). All
three mirrors now exclusively host long-filename IGS20 products.

**Silent failure mode:** `download_product()` returns `None` with a log warning —
no exception raised. Bernese BPE runs with no orbit/clock files staged.

---

## Bugs in Current Code

| Line | Bug | Impact |
|------|-----|--------|
| 34 | `f"cod{gps_week}{gps_dow}.sp3.Z"` — short name + `.Z` compression | Wrong filename format (retired 2022) |
| 34 | Uses GPS day-of-week (`gps_dow`) instead of day-of-year (`ddd`) | IGS20 names need DOY, not DOW |
| 14–16 | CDDIS in mirror list; no auth mechanism | CDDIS requires Earthdata Login since Oct 2020; returns 401 |
| 14–16 | IGN URL: `/pub/igs/products/` | Correct path; confirmed |
| 44–45 | `{mirror}{gps_week}/{filename}` — week-dir structure is correct | Only filename is wrong |
| — | No `gzip` import or decompression logic | All new files are `.gz` |
| — | No DOY calculation | Required for long filename construction |

---

## IGS20 Naming Convention

**Transition date:** GPS week 2238 = **27 November 2022**. Hard cutoff — no legacy
short names on live servers after this date. `.Z` compression retired; `.gz` is standard.

### Long Filename Template

```
AAA 0 OPS TYP _ YYYY DDD HHMM _ LEN _ SMP _ CNT . FMT . gz
```

| Field | Width | Meaning | Fixed values |
|-------|-------|---------|-------------|
| `AAA` | 3 | Analysis Centre | `IGS`, `COD` |
| `0` | 1 | Version (always 0 for operational) | `0` |
| `OPS` | 3 | Campaign | `OPS` (operational) |
| `TYP` | 3 | Solution type | `FIN` (final) |
| `YYYY` | 4 | UTC year | e.g. `2024` |
| `DDD` | 3 | Day of year (001–366) | e.g. `099` |
| `HHMM` | 4 | Start time (daily = `0000`) | `0000` |
| `LEN` | 3+1 | Duration | `01D` |
| `SMP` | 3+1 | Sampling interval | `15M`, `05M`, `30S` |
| `CNT` | 3 | Content type | `ORB` (orbits), `CLK` (clocks) |
| `FMT` | — | Format | `SP3`, `CLK` |

### Concrete File Names

```
# IGS combined — orbits and clocks
IGS0OPSFIN_${yyyy}${ddd}0000_01D_15M_ORB.SP3.gz    # orbits, 15-min sampling
IGS0OPSFIN_${yyyy}${ddd}0000_01D_05M_CLK.CLK.gz    # clocks, 5-min sampling
IGS0OPSFIN_${yyyy}${ddd}0000_01D_30S_CLK.CLK.gz    # clocks, 30-sec (satellite)

# CODE Bern GPS-only finals (matches PHIVOLCS V_SATSYS = GPS)
COD0OPSFIN_${yyyy}${ddd}0000_01D_05M_ORB.SP3.gz
COD0OPSFIN_${yyyy}${ddd}0000_01D_30S_CLK.CLK.gz

# CODE Bern Multi-GNSS finals (GPS + GLONASS + Galileo + BeiDou)
COD0MGXFIN_${yyyy}${ddd}0000_01D_05M_ORB.SP3.gz
COD0MGXFIN_${yyyy}${ddd}0000_01D_30S_CLK.CLK.gz
```

**Which product for PHIVOLCS?** `PHIVOL_REL.PCF` sets `V_SATSYS = GPS` and `V_B = IGS`.
`COD0OPSFIN` (GPS-only) is sufficient. `COD0MGXFIN` adds value only if constellation
is expanded to include GLONASS/Galileo in future campaigns.

**Legacy short names (pre-GPS week 2238) for reference:**
```
cod{wwww}{d}.sp3.Z      # CODE orbits, e.g. cod22380.sp3.Z
igs{wwww}{d}.sp3.Z      # IGS combined, e.g. igs22380.sp3.Z
igs{wwww}{d}.clk.Z
igs{wwww}{d}.clk_30s.Z
```

---

## Server Directory Structure

### Directory path (all three servers)
```
{base_url}/{wwww}/{filename}
```
`{wwww}` = 4-digit GPS week, zero-padded (e.g. `2309`)

### Mirror URLs

| Server | Base URL | Auth | Notes |
|--------|----------|------|-------|
| **IGN** | `https://igs.ign.fr/pub/igs/products/` | None — anonymous | **Primary mirror; use first** |
| **BKG** | `https://igs.bkg.bund.de/root_ftp/IGS/products/` | None — anonymous HTTP | Second fallback |
| **CDDIS** | `https://cddis.nasa.gov/archive/gnss/products/` | Earthdata Login required | Third fallback; needs `.netrc` |

### Recommended fallback order
```
IGN → BKG → CDDIS
```
IGN and BKG are anonymous; avoid requiring EARTHDATA credentials for a working baseline.
CDDIS is last resort — wire in only if the others fail and credentials are available.

### Example full URLs
```
# IGN
https://igs.ign.fr/pub/igs/products/2309/IGS0OPSFIN_20240990000_01D_15M_ORB.SP3.gz
https://igs.ign.fr/pub/igs/products/2309/COD0OPSFIN_20240990000_01D_05M_ORB.SP3.gz

# BKG
https://igs.bkg.bund.de/root_ftp/IGS/products/2309/IGS0OPSFIN_20240990000_01D_15M_ORB.SP3.gz

# CDDIS
https://cddis.nasa.gov/archive/gnss/products/2309/IGS0OPSFIN_20240990000_01D_15M_ORB.SP3.gz
```

---

## Implementation Checklist for Next Session

The rewrite is entirely within `packages/pogf-geodetic-suite/src/pogf_geodetic_suite/igs_downloader.py`.
No new dependencies needed (`requests` and `gzip` are already available / stdlib).

- [ ] Add DOY calculation (`date.timetuple().tm_yday`, zero-pad to 3 digits)
- [ ] Keep GPS week calculation (already correct in `_get_gps_week_dow`)
- [ ] Build long filename from template: `{ac}0OPSFIN_{yyyy}{ddd}0000_01D_{smp}_{cnt}.{fmt}.gz`
- [ ] Product table: map `(ac, content)` → `(smp, fmt)`:
  - orbits → `15M` for IGS, `05M` for CODE; format `SP3`
  - clocks → `30S`; format `CLK`
- [ ] Update mirror list: IGN primary, BKG second, CDDIS third
- [ ] Add `.gz` decompression (`gzip.open` or `gzip.decompress`)
- [ ] Optional: `.netrc` auth path for CDDIS (low priority; IGN/BKG cover normal use)
- [ ] Add legacy fallback for dates before GPS week 2238 if historical data needed
- [ ] Write unit tests:
  - filename construction for a known date (verify against table above)
  - DOY calculation edge cases (Jan 1, Dec 31, leap year day 366)
  - Mirror fallback (mock 404 on first mirror, verify second is tried)
- [ ] Verify against live server with a known historical file before wiring into BRN-004

---

## Remaining Uncertainties (low risk)

- IGN/BKG mirror HTTPS URLs confirmed from docs, not live-probed — verify with a `curl -I` at session start
- CDDIS `.netrc` auth from Python `requests.Session` — needs one live test if CDDIS fallback is wired in
- DOY vs GPS DOW in directory path: confirmed DOY in filename, GPS week in directory — no ambiguity

---

## Sources

- IGS Guideline for the transition to IGS20 and long filenames v2.1
  `https://files.igs.org/pub/resource/guidelines/Guidelines_for_Long_Product_Filenames_in_the_IGS_v2.1.pdf`
- IGSMAIL-8282: Switch of IGS products to IGS20 and long filenames
- CDDIS Archive Access — NASA Earthdata
- BKG GNSS Datacenter: `https://igs.bkg.bund.de/`
