# Provenance of the captured PAGENET assets

**Captured 2026-08-03 from the T420** (`/home/finch/GPSUSER/`), the machine that
drove the June–July 2026 PAGENET training week. Requested by the gps3 session in
`docs/gps3-sessions/SESSION_LOG_20260729_storage.md` §14.5, which is right that
these must be **captured, not re-derived**.

Copied byte-for-byte. Nothing was sanitized on the way in — the point of a
capture is to record what actually ran, hazards included. What follows is what
you are getting, checked against the files rather than assumed.

---

## `PCF/PAGENET_DLY.PCF`

5,979 B, last modified 2026-06-26. Drove the full training week.

**It has no dangling `WAIT`.** §14.5 anticipated `599 DUMMY` waiting on
`512 514 522`, leaving 522 undefined once the R2S_RED branch is dropped. That
describes stock `RNX2SNX.PCF`, not this file. The actual tail:

```
511  ADDNEQ2   PGN_FIN   CPU=ANY; WAIT=502
512  GPSXTR    PGN_FIN   CPU=ANY; WAIT=511
513  HELMCHK   PGN_FIN   CPU=ANY; WAIT=511; NEXTJOB=511
514  COMPARF   PGN_FIN   CPU=ANY; WAIT=513
599  DUMMY     NO_OPT    CPU=ANY; WAIT=512 514
```

There is no 521/522 anywhere in the file, and **no `9xx` save/cleanup tail** —
599 is the last PID. The adaptation §14.5 worried about performing by eye had
already been done, deliberately, by whoever built this PCF. The provisioner's
dangling-WAIT check should pass it unmodified.

Two variables the readiness doc cares about, for reference:
`V_CLUFIN = A` (the P2-K tuning target, still untuned) and `V_CLU = 10`.

---

## `OPT/PGN_WK/`

Six panels. **`ADDNEQ2.INP` is already sanitized**; the others are not.

A "phase B" edit on 2026-07-03 converted this panel from the instructor's
Windows-built original. Diffing it against the retained backup
(`ADDNEQ2.INP.pre_phaseB_20260703`, **not committed** — 186 KB of near-duplicate)
shows exactly what changed:

| Change | From → To |
|---|---|
| Path separators | `${MODEL}\CONST.BSW`, `${CONFIG}\DATUM.BSW`, `${U}/WORK\ERROR.MSG` … → forward slashes throughout |
| `ENVIRONMENT` block | `"U" "C:\Bernese\GPSUSER54\"`, `"P" "C:\Bernese\CAMPAIGN54\"`, `"USER" "LAB-06"` → `ENVIRONMENT 1 "" "${}"` |
| `INPFILE` | the instructor's 3 demo sessions `20261030/40/50` → the **7 real PAGENET sessions** `20260840`–`20260900` |
| Campaign | `${P}/SOB` (instructor's campaign) → `./DUMMY` |
| `MAXPAR` | **5000 → 10000** |

`MAXPAR` matters: the readiness notes record the ADDNEQ2 parameter overflow, and
this panel is already past it. Do not "fix" it back down.

### Hazards that remain — expect the provisioner to catch these

1. **Two hardcoded demo-week literals survive in `ADDNEQ2.INP`**, both pointing
   at the instructor's DOY 104 rather than any PAGENET session:
   - line 66 — `COORD 1 "./DUMMY/STA/$(FIN)_20261040.CRD"`
   - line 935 — `FREESTA_F 1 "./DUMMY/STA/REF_20261040.FIX"`

   These need remapping to the session being processed.

2. **`MENU.INP` still carries Windows separators and the instructor's campaign
   name** — the one file the phase B pass did not touch:
   ```
   SESSION_TABLE 1  "${P}/SOB\GEN\SESSIONS.SES"
   ```
   `SOB` is the instructor's campaign, and on Linux `\` is a literal character,
   not a separator. Note this also points `SESSION_TABLE` at a **per-campaign**
   `SESSIONS.SES`, which is the correct location — see the "looks broken but is
   not" note in `docs/GPS3_SESSION_HANDOVER_20260729.md`.

   > **Verified 2026-08-04, and this file was listed under "expect the
   > provisioner to catch these" when it did not.** Running
   > `sanitize_panel_text()` over `MENU.INP` as of PR #64 returned
   > `changed=True, warnings=0`: the backslashes were silently converted and the
   > panel reported **clean**. The hardcoded `SOB` matched no hazard class —
   > `foreign_abs_path` wants a drive letter, `hardcoded_session` wants a date
   > stamp — so the instructor's campaign name would have reached `$U` unflagged.
   >
   > A `hardcoded_campaign` class was added to close this
   > (`_HARDCODED_CAMPAIGN_RE`, matching `${P}/<literal>`). Both `MENU.INP` and
   > **`MENU_CMP.INP`** — which this list does not mention at all — now raise 2
   > warnings each, and the strict gate refuses the tree until they are remapped.
   >
   > The general point, since it recurs: a hazard listed in a provenance
   > document is a *claim about tooling*, and it is worth running the tool to
   > confirm it before writing the claim down. Two of the assertions in these
   > two files were wrong in the direction of false reassurance.

3. **`./DUMMY/...` relative paths** throughout `ADDNEQ2.INP` are a campaign
   placeholder, not a real directory.

### Not committed, deliberately

`ADDNEQ2.bck` and `ADDNEQ2.INP.pre_phaseB_20260703` — 186 KB each, and both are
the pre-sanitization state, which this file now records in diff form. They
remain on the T420 at `/home/finch/GPSUSER/OPT/PGN_WK/` if the original is ever
needed as evidence.
