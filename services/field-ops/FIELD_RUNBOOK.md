# Field Ops runbook — recording a station visit

**Audience:** the observer holding the phone. Provisioning the URL, database and
photo storage is a different job and lives in `DEPLOY.md`.

A rendered version for sharing with staff is published as an Artifact; this file
is the source of truth and the two are generated together.

---

## Read this first

**Your sheets live on the phone until they sync.** Clearing browsing data,
clearing site storage, or uninstalling the app deletes every unsynced sheet *and
its photo*. There is no copy anywhere else. Do none of those things until the
Queue screen shows nothing waiting.

---

## 1. Before you leave — at the office, on wifi

The app must be opened once with a working connection. That first load caches
the app itself and downloads the station and observer lists. Skip it and the app
will not open at the monument.

- [ ] Open the URL you were sent. **Install it to the home screen** when offered.
- [ ] Sign in with the account issued to you. One account per person.
- [ ] Check the **Station** dropdown lists the sites you are actually visiting.
- [ ] Check your initials appear under **Observers**.
- [ ] File one throwaway sheet and confirm *"Saved and synced to server."*
- [ ] Charge the phone.

**Sign in each morning.** A session lasts 8 hours and can expire while you are
out. Nothing is lost when it does, but the app will ask you to sign in again
before it can sync.

### If you are told the app has been updated

**Close it completely and open it again — twice if you want to be sure.**

The app keeps a copy of itself on the phone so it works with no signal. When a
new version is published, that copy is replaced in the background, but whatever
is already open keeps running the old one until the app is fully closed and
reopened. Swiping back to the home screen is not enough on most phones; close it
from the app switcher.

This matters because the symptom is confusing: you are told a problem was fixed,
you go back to the app, and the problem is still there. Nothing is wrong — you
are looking at yesterday's copy. Queued sheets are not affected either way; they
live separately and survive the update.

## 2. At the station — signal or no signal

**Monitoring method** decides the rest of the form: *Campaign GPS* asks for
antenna model, slant heights and session times; *Continuous (CORS
Maintenance)* asks for power and battery.

**Station** is grouped Active / Under maintenance / Decommissioned–archived. All
are selectable — a station under maintenance is one you were sent to because it
needs work.

**The photo is not optional.** Submit stays disabled until one is attached. It
is the only record of what the site looked like and the one thing nobody can
reconstruct later.

Offline, a yellow banner says sheets are saved on the device. That is normal;
submitting offline is not a degraded mode.

**If it says there is not enough storage:** nothing was saved — not the sheet,
not the photo. The form keeps what you typed. Sync pending sheets to free space,
then submit again before leaving the station.

### Continuous (CORS) visits — write down what is installed

The form asks for the **receiver and antenna as you found them**: model, serial,
firmware, antenna type, part and serial numbers, and the vertical antenna height.
Copy them off the labels on the hardware. **If something is not marked, leave it
blank** — a guessed serial is worse than an empty box, because it looks like a
reading.

For Palawan this is the first time PPPC, PNDO and PKLY will have their hardware
recorded anywhere; there is nothing on file to check against.

If you swap anything during the visit, tick **Equipment was changed** and fill in
what it was changed *to*. The form will not accept the tick on its own: a sheet
saying "something was changed" without saying what destroys the only record of
it. Leave unchanged items blank in the second block.

## 3. When signal comes back

Sync happens by itself the moment the phone has a connection. **Sync now** on
the Queue screen exists because signal often returns as a brief window.

A sheet is marked synced only once *both* the form and its photo have reached
the server.

**Before leaving the area, get the Queue to nothing waiting.** A sheet still
pending when you go back out of coverage stays pending until the next time you
have signal.

## 4. What the app is telling you

| The app says | What it means | What to do |
|---|---|---|
| Saved and synced to server. | Form and photo are on the server. | Nothing. |
| Saved offline — including the photo. | On the phone, not the server. Normal offline. | Check the Queue when you have signal. |
| Log saved. Photo queued. | Sheet reached the server; photo held on the phone. | Nothing — photo goes on the next sync. |
| Log saved on the server — but the photo could not be uploaded or stored. | Sheet is safe. **Photo is not saved anywhere.** Phone is out of space. | Free space, re-attach the photo from the form. Do not leave the site. |
| The server is not responding. | Connection is up; server did not answer. | Nothing lost. Sync again later. |
| N sheets were refused by the server. | Something on those sheets is wrong — usually an observer no longer on the staff list. | Reason is printed under each. Correct, then **Try again**. |
| Not enough device storage. | Nothing was saved. | Sync to free space, submit again. |
| Please sign in again | The 8-hour session expired. | Sign in; queued sheets sync straight after. |

## 4a. Checking what has been filed

The **Sheets** tab lists everything that has reached the server, newest first —
every team's, not only yours. Use it at the end of the day to confirm your own
visits are in, and to see what other teams filed elsewhere.

Two things it will show you that matter:

- **photo pending** — the sheet is on the server and its photo is not. Chase
  this one: it means the photo is still on somebody's phone.
- **On this device, not yet sent** — a separate list above the table, and only
  ever from the handset you are holding.

**A sheet still sitting on a colleague's phone cannot appear here at all.** An
empty row for someone else's station means "not synced yet", not "not visited".

## 4b. Reporting a problem, or an idea

Two forms, both plain-language, at:

    https://github.com/alfieprojectsdev/movefaults/issues/new/choose

- **Something is wrong in the app** — it did something unexpected, or would not
  let you work.
- **Something is missing, or could be easier** — a field it should ask for, a
  step that takes too long. Nothing is too small; something mildly annoying
  twenty times a week is exactly what is worth changing.

The forms ask which part of the app, which station and roughly when, whether you
had signal, and whether any work was lost. Answer what you can and leave the
rest blank — a short report beats no report.

**Two things to know before you use it:**

1. **The page is public.** Anyone on the internet can read what you write.
   Never type your password, not even to show it did not work, and do not
   attach a screenshot showing one. Station codes, times and error messages are
   all fine.
2. **It needs a free GitHub account** — an email address and a password, a few
   minutes once. If you would rather not, message Alfie with the same details
   and he will file it for you. Do not skip reporting because of the account.

## 5. Back at the office — same day

- [ ] Confirm the Queue shows **nothing waiting**.
- [ ] Report anything still *refused* — those need database access.
- [ ] Only then clear the phone or pass it on.

A phone wiped with sheets still queued loses them permanently, and silently.

## 6. Known gaps — decide before departure

**The station list is continuous CORS only.** All 138 seeded stations are
continuous. No campaign sites are loaded; if the team is doing campaign
occupations, those sites must be added first.

**Palawan coverage is thin.** `PLWN` (Brooke's Point) is the only Palawan site
in PHIVOLCS' own inventory and has no coordinates. `PPPC`, `PNDO` and `PKLY` are
NAMRIA's, marked as theirs.

**Antenna height arithmetic is now checked, but keep the paper record.** The
campaign form's reduction — RH = sqrt(mean slant^2 - C^2) - VO — matches the
formula in PHIVOLCS' own `antenna_height_conversion` workbooks exactly, and the
per-model constants are pinned by tests against both those workbooks and
Trimble's antenna diagrams.

One constant was wrong until 2026-08-20: **TRM22020.00+GP** (Compact L1/L2 with
ground plane) used the vertical offset to the *top* of the ground plane instead
of the bottom, which made every RINEX height from that antenna 3.5 mm too short.
No campaign sheet had been filed at that point, so nothing needs recomputing —
it was caught before the first fieldwork, not after.

**Three slant readings are enough.** Measure all four when you can — opposing
pairs cancel a tilted tripod, which is the whole reason four are taken. When a
leg, a wall or the monument blocks one, enter the three you have and note in the
log why. The form will say it is averaging three, and name the direction you
skipped. Two is refused: it may not even be an opposing pair.

**Write the raw slant measurements in the paper log anyway.** The
arithmetic being right does not make a mistyped tape reading recoverable, and
the raw numbers are what lets a height be recomputed if a constant moves again.

**Offline launch is untested on a real phone.** Filing and syncing offline are
verified. Opening the app from the home screen with no signal depends on the
service worker, which has not been exercised on a handset — test it before
departure: install, airplane mode, open.
