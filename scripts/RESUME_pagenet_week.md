# PAGENET 7-day weekly — RESUME (halted 2026-06-26 15:25, training ended)

## State at halt
- DONE (FIN NQ in $P/PAGENET/SOL/): 084, 085, 086  (3 of 7)
- REMAINING: 087, 088, 089, 090
- 087 was killed cleanly at RNXGRA (early) — no partial output, no locks.
- PLG2 station stashed in $D/PGN/.excluded_plg2/ (unlisted in PGN.STA; needed for 088).
  Leave it stashed — keeps the 7-day network consistent.

## To resume (from $HOME):
    source ~/BERN54/LOADGPS.setvar
    setsid nohup bash ~/chain_days.sh 087 088 089 090 > ~/bernese_chain_086-090.log 2>&1 < /dev/null &

## Then re-arm the watch (optional, in a Claude session):
    bash ~/watch_chain.sh   # NOTE: edit it first — it checks for 5 NQ (086-090);
                            # now only 4 remain (087-090). Change the loop to those 4.

## Per-day ~2h on T420 (502 GPSCLU_P final solve dominates). 4 days ≈ 8h.

## Known snag: 088 has PLG2 → already stashed → immune (same fix that recovered 086).
## Watch for: any day tripping PID 322 (PTAG troposphere, data-dependent) → exclude PTAG that day, resume.

## After all 7 dailies land → Phase B + C:
- Phase B: fix $U/OPT/PGN_WK/ADDNEQ2.INP  (\ -> /, point inputs at $P/PAGENET/SOL/FIN_$YYYSS,
  anchor session 090, VAR_MINUS=-6 VAR_PLUS=0). Same for PGN_MO if running ADD_MON.
- Phase C: run ADD_WK (PID 530) = the weekly combined solution. The actual Module 15 deliverable.
