# Three questions for the processing team

**For discussion with Cass and the GNSS processing group. Prepared 2026-08-24.**

None of these blocks the 2025 reprocessing, which is already under way. Each is
a place where the answer has to come from how the group actually works, not
from the software. Written down so the discussion starts from the same facts.

---

## 1. Rapid results after a major earthquake

**Today:** when a large earthquake happens, someone stages rapid or ultra-rapid
orbits by hand and runs a solution to get coordinates before the final orbits
are available. This has been done since at least 2013. It is not written down
anywhere.

**Proposal:** set this up as a standing option, so it can be run on request
instead of assembled under pressure.

**Why it is sound, not a shortcut.** A coseismic offset is tens of centimetres.
Ultra-rapid orbits are good to roughly five centimetres. That is more than
enough to answer *"how far did the ground move?"* — which is the question being
asked in the first hours. It is **not** enough for velocities, where we are
chasing a few millimetres per year and a two-centimetre bias would matter.
Different orbit, different question.

**What we need from you:**

- What you actually do now — which stations you include, how long you wait for
  orbit coverage, and what you do when the available orbits only partly cover
  the day.
- Agreement on one rule: **rapid results are labelled as rapid, and never enter
  the velocity series.** If they mix in, a difference in orbit quality shows up
  in the time series looking exactly like real ground movement, and nothing
  downstream can tell the difference afterwards.

---

## 2. When should processing stop and ask for a human?

**Today:** every daily run already checks its reference stations — whether each
one sits where the reference frame says it should. **Nothing acts on the
result.** A reference station that had genuinely moved would pass through
unremarked, and every coordinate computed against it would be shifted with it.

**Precedent:** Japan's Geospatial Information Authority set a threshold of
2 ppm estimated strain. Above it they suspended survey data — 438 control
stations — until a revised datum was published. A deliberate freeze, not an
automatic correction.

**What we need from you:**

- A threshold. What size of discrepancy at a reference station should stop the
  day's solution from being used?
- Who is told, and who decides to release it.

The software can flag and hold. It should not decide that a station moved.

---

## 3. The discontinuity list for continuous stations

**Background:** the `offsets` file for campaign sites was copied into version
control on 12 August — 88 records, 70 sites, 2003 to 2026, recording which
coordinate jumps were earthquakes, eruptions, or equipment changes. It existed
only on one Windows machine and on staff computers. It cannot be reconstructed
from the coordinates; it is accumulated judgement.

**The gap:** the equivalent list for **continuous stations** has not been
found or copied. ALBU is the clear example — its time series plainly shows
jumps at the 2017 Ormoc and 2025 Bogo earthquakes, but ALBU appears in no
discontinuity file we hold.

**What we need from you:**

- Where that list lives, and who maintains it.
- Permission to take a read-only copy into version control, as was done for the
  campaign list. Nothing on the server is changed, moved, or deleted.

**This half is worth doing before the meeting rather than after** — it is a
copy, not a decision. What needs discussing is how the list should feed the
processing, not whether a second copy should exist.

---

## What is not being asked

Whether to automate more. The agreed direction is unchanged: automate the
routine handling as far as it will go, and keep the judgement — which points
are outliers, which jumps are real, whether a station moved — with the people
who can make it. Every item above is about **giving that judgement better
information sooner**, not about removing it.
