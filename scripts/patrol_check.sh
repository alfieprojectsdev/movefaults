#!/usr/bin/env bash
# patrol_check.sh — determine whether ANYTHING performs full-surface reads of
# the 16 PERC members, without iDRAC and without vendor tools.
#
# THE PROBLEM. This is a 16-wide RAID 5: one drive of redundancy. A rebuild
# reads all 15 survivors, and a single latent unreadable sector during that
# zero-redundancy window can lose the array. Surface scanning is what finds
# those sectors while parity still exists to repair them. The PERC's own patrol
# read is the usual answer, but its configuration is NOT exposed to Linux, no
# vendor CLI (storcli/perccli/megacli) exists in the Ubuntu repos, and iDRAC has
# no IP. The question looked unanswerable from the OS.
#
# THE ANSWER. It is answerable, because scanning need not come from the
# controller. SAS drives run their own Background Media Scan (BMS) in firmware,
# below the RAID layer, and both its scan log and the lifetime byte counters are
# readable through the megaraid pass-through. What this script measures is BMS,
# not patrol read — and that is sufficient, because both defend the same failure
# mode and only one of them has to be running.
#
# THE METHOD. Scan count and lifetime-bytes-read are separate firmware counters
# kept for unrelated purposes. If (scans x capacity) lands near the lifetime read
# total, the scans genuinely traverse the whole surface. That agreement between
# two independent counters — the SWEEPS column — is what makes this a conclusion
# rather than a guess about what a single number's label means.
#
# Measured on gps3 2026-08-03: ~425 scans/drive over 10,145 power-on hours,
# SWEEPS 1.01x on all 16, zero uncorrected errors. Full-surface reads happen
# roughly daily. SMART long tests were considered and rejected as duplicative.
#
# READ-ONLY. Usage: sudo bash patrol_check.sh
set -uo pipefail

VD=/dev/sda
N=16

printf '%-4s %-12s %-8s %-8s %-13s %-9s %s\n' \
  "ID" "READ (TB)" "UNCORR" "SCANS" "RECOV(phys)" "SWEEPS" "BMS STATUS"
printf '%s\n' "---------------------------------------------------------------------------------"

total_read=0
total_rec=0
for id in $(seq 0 $((N-1))); do
    # Capture then parse. Never `smartctl | grep` under pipefail — grep -q
    # exits early, smartctl takes SIGPIPE, and the pipeline returns 141 even
    # on success. That bug reported "0 of 16 healthy drives" on 2026-07-30.
    err=$(smartctl -l error -d "megaraid,$id" "$VD" 2>/dev/null)
    bg=$(smartctl -l background -d "megaraid,$id" "$VD" 2>/dev/null)
    inf=$(smartctl -i -d "megaraid,$id" "$VD" 2>/dev/null)

    # COLUMN ORDER (verified against raw output 2026-08-03 — do not "tidy" this):
    #
    #     Errors Corrected by        Total   Correction   Gigabytes   Total
    #         ECC       rereads/    errors   algorithm    processed   uncorrected
    #     fast|delayed  rewrites  corrected  invocations [10^9 bytes]  errors
    #   read:   0   228     228       228       3929    1025339.394      0
    #
    # "Gigabytes processed" is $(NF-1). "Total uncorrected errors" is $(NF).
    # The first version of this script had those two swapped, which printed
    # 0.00 TB read and 1,025,339 uncorrected errors — a drive that looked
    # both unscanned and catastrophically failing, when it was neither. The
    # numbers were individually plausible, which is exactly why it survived
    # a first reading. Same failure family as the SIGPIPE bug in
    # smartd_setup.sh: a value taken from the wrong place, yielding a
    # confident and precisely inverted answer.
    rgb=$(printf '%s\n' "$err" | awk '/^read:/  {print $(NF-1)}' | head -1)
    unc=$(printf '%s\n' "$err" | awk '/^read:/  {print $(NF)}'   | head -1)

    # BMS = Background Media Scan, run by the DRIVE firmware, below the RAID
    # controller. This is independent of PERC patrol read: BMS being active
    # says nothing about patrol read, and vice versa. We report BMS because
    # it is the one we can actually observe without iDRAC or a vendor CLI.
    scans=$(printf '%s\n' "$bg" | grep -oE 'Number of background scans performed: *[0-9,]+' \
            | grep -oE '[0-9,]+$' | tr -d ',' | head -1)
    poh=$(printf '%s\n' "$bg" | grep -oE 'power on time, hours:minutes +[0-9]+' \
          | grep -oE '[0-9]+$' | head -1)
    status=$(printf '%s\n' "$bg" | grep -oE 'Status: .*' | head -1 | cut -c9-38)

    # Rows of the recovered-sector table, e.g.
    #   1 7725:11  0000000000b57030  [1,18,7]  Recovered via rewrite in-place
    # Each is a latent bad sector BMS found and repaired while the array still
    # had full redundancy — i.e. the failure that kills a rebuild, defused.
    rec=$(printf '%s\n' "$bg" | grep -cE '\[[0-9]+,[0-9]+,[0-9]+\]')

    # UNITS — this column was misread once, on 2026-08-03, and it matters.
    # These are 512e drives: 4096-byte PHYSICAL sectors presented as 512-byte
    # LOGICAL ones. A single weak physical sector therefore logs as EIGHT
    # consecutive entries. Member 6 read as "671 defects", seven times its
    # nearest peer and alarming enough to consider proactive replacement — but
    # 671/8 = ~84 physical sectors, and that drive's corrected-read-error
    # counter independently read exactly 84. The raw entry count overstates
    # the defect count by ~8x. Report both: the raw number for auditability,
    # the physical estimate for judgement.
    recp=$(( rec / 8 ))

    # Capacity, for the sweep cross-check below.
    capb=$(printf '%s\n' "$inf" | grep -oE 'User Capacity: *[0-9,]+' \
           | grep -oE '[0-9,]+$' | tr -d ',' | head -1)

    [ -z "$rgb" ] && rgb="?"; [ -z "$unc" ] && unc="?"
    [ -z "$scans" ] && scans="?"; [ -z "$rec" ] && rec=0
    [ -z "$status" ] && status="(no background scan log)"

    rtb=$(awk -v g="$rgb" 'BEGIN{ if (g+0==g) printf "%.2f", g/1000; else print "?" }')

    # THE CROSS-CHECK, and the reason this script can conclude anything at all.
    # Scan count and bytes-read are two counters the firmware maintains for
    # different purposes. If (scans x capacity) lands near the lifetime read
    # total, the scans really are reading the whole surface — verified by two
    # independent paths rather than by trusting one number's label.
    if [ "$rgb" != "?" ] && [ "$scans" != "?" ] && [ -n "$capb" ]; then
        sweeps=$(awk -v g="$rgb" -v s="$scans" -v c="$capb" \
                 'BEGIN{ if (s>0 && c>0) printf "%.2fx", (g*1e9)/(s*c); else print "-" }')
    else
        sweeps="-"
    fi

    [ "$rgb" != "?" ]  && total_read=$(awk -v t="$total_read" -v g="$rgb" 'BEGIN{print t+g}')
    total_rec=$((total_rec + rec))

    printf '%-4s %-12s %-8s %-8s %-13s %-9s %s\n' \
      "$id" "$rtb" "$unc" "$scans" "$recp ($rec)" "$sweeps" "$status"
done

echo
printf 'combined lifetime read across all 16 members: %.2f TB\n' \
  "$(awk -v t="$total_read" 'BEGIN{print t/1000}')"
printf 'sectors repaired by BMS, array-wide: ~%s physical (%s logical entries)\n' \
  "$((total_rec / 8))" "$total_rec"
[ -n "${poh:-}" ] && printf 'power-on time: %s hours (%.1f days)\n' \
  "$poh" "$(awk -v h="$poh" 'BEGIN{print h/24}')"
echo
cat <<'EOF'
HOW TO READ THIS
  The array holds a few hundred GB and has seen almost no host I/O, so any
  large read total must come from something sweeping the surface.

  SWEEPS is the load-bearing column: lifetime bytes read divided by
  (scan count x drive capacity).

    ~1.00x  -> each background scan reads the drive end to end. Full-surface
               coverage is real. Nothing more is needed; do NOT add SMART long
               tests -- they would duplicate this and add load for no gain.
    <<1.00x -> scans are counted but are not reading the whole surface.
    "-"     -> not enough data to judge; read the raw smartctl output.

  SCANS with a large READ total and SWEEPS near 1.00x is the healthy case.
  SCANS near zero, or a READ total comparable to the data actually stored,
  means nothing is doing full-surface reads: latent bad sectors accumulate
  unseen until a rebuild trips over one. Fix by enabling patrol read
  (iDRAC/perccli) or adding staggered long tests:
      -s (S/../.././NN|L/../../6/NN)

  RECOV(phys) counts sectors BMS found weak and repaired in place while the
  array still had full redundancy. A non-zero number is GOOD NEWS -- it is the
  mechanism working on sectors that would otherwise have surfaced mid-rebuild,
  with no parity left to reconstruct them from.

  UNITS: shown as "physical (logical)". These are 512e drives, so ONE 4K
  physical sector logs as EIGHT consecutive 512-byte entries. Judge by the
  physical number. Reading the raw count on 2026-08-03 made member 6 look
  7x worse than its peers and nearly triggered a proactive replacement;
  divided by 8 it was ~84 sectors, matching that drive's own corrected-error
  counter exactly.

  WHAT ACTUALLY INDICATES A DYING DRIVE -- the count alone does not:
    * reassign_status other than "Recovered via rewrite in-place".
      "Reassigned" consumes a spare; "Reassign failed" means data was lost.
    * Defects CLUSTERED IN RECENT power-on hours. Spread evenly across the
      drive's whole life is slow wear; a recent burst means something changed.
    * UNCORR above 0, ever.
  Member 6 had 671 logical entries and none of these three. Member 0 had zero
  entries but 228 corrected read errors and 3,929 correction invocations --
  it works harder to read its data. Ranking drives by entry count alone picks
  the wrong suspect. Use scripts/sudo/inspect_member6.sh to examine one drive.

  UNCORR (total uncorrected read errors) is the one that must stay 0.
  Non-zero means data the drive could not return -- act on it immediately.

  SCOPE: BMS is the drive firmware's own scan, below the RAID controller.
  It says NOTHING about whether PERC patrol read is enabled. It does not
  need to: both defend the same failure mode, and BMS is the one visible
  from the OS without iDRAC or a vendor CLI.
EOF
