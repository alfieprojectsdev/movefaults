# Field Ops UI screenshots

Captured **2026-08-22** from the live deployment at `movefaults.vercel.app`
during an end-to-end test. Two complete sets, **identical filenames**, so a
consumer switches theme by changing one path component:

```
dark/    15 files    the app's dark theme
light/   15 files    the app's light theme
```

## Capture conditions

| | |
|---|---|
| Viewport | **500 × 697 CSS px** |
| Theme forced by | `localStorage.setItem("field_ops_theme", "light" \| "dark")` before load |
| Signed in as | `ARP` (admin) |
| Deployment | Vercel frontend, Render API, Neon Postgres |

**Why 500 px and not 390.** Chrome on Linux refuses to size a window below
roughly 500 px wide, so a true iPhone viewport was not reachable from an
automated session. The layout is in its single-column mobile form at this
width — what these show is what a handset shows, one notch wider.

**Theme was set through `localStorage`, not the ☀/◐ toggle**, because the
toggle cycles `system → light → dark` and driving it blind means guessing the
starting state. The key and its three values are defined in
`frontend/src/hooks/useTheme.ts`.

## What is in them

| File | Shows |
|---|---|
| `01-sign-in.jpg` | Sign-in screen |
| `02-new-log-sheet-top.jpg` | Form head: method, station, date, arrival |
| `03-method-campaign-station-selected.jpg` | Campaign GPS + station chosen |
| `04-observers-technical.jpg` | Observer picker, TECHNICAL group |
| `05-observers-admin-scrolled.jpg` | Observer picker, ADMIN group (inner list scrolled) |
| `06-antenna-setup-empty.jpg` | Antenna section before entry |
| `07-slants-three-of-four-warning.jpg` | Three slants entered — "3 of 4" and the tilt-bias note |
| `08-rinex-height-and-session.jpg` | Computed RINEX height, session block |
| `09-session-photo-submit-disabled.jpg` | Photo required, Submit greyed out |
| `10-continuous-power-battery.jpg` | Continuous: power notes, battery voltage |
| `11-continuous-equipment-as-found.jpg` | Equipment as found |
| `12-equipment-as-left-block.jpg` | "Equipment as left" revealed by the tick |
| `13-equipment-changed-refusal.jpg` | The bare tick refused, Submit still disabled |
| `14-queue-nothing-waiting.jpg` | Queue with nothing pending |
| `15-sheets-filed-empty.jpg` | Sheets tab |

## Disclosure — read before adding more

This repository is **public**.

What these images contain, deliberately checked before committing:

- **Staff initials** (8 of 13 visible across `04` and `05`). Already public:
  `data/network_inventory/staff.csv` is committed and carries `full_name` for
  all 13. These add nothing new.
- **Station codes and names** — public CORS sites.
- **No credentials.** Both `01-sign-in.jpg` files were captured with the
  username and password fields cleared; the browser had autofilled them and
  they were emptied before the shot.
- **No logsheet contents.** The server held no filed sheets at capture time.

**If you add screenshots here, check the same things.** The username scheme is
staff initials (see `scripts/seed_field_accounts.py`), so an image showing a
filled sign-in form would publish a real username. Passwords are random since
2026-08-19, which limits the damage, but do not publish one anyway.

## Regenerating the quick guide

The operator guide is generated from these:

```
python temp/guide-build/build_guide.py          # dark  (default)
python temp/guide-build/build_guide.py light    # light
```

That script is **not** tracked — it lives in the gitignored `temp/` working
area along with its `.docx` output, because the guide is distributed to field
staff rather than versioned here. If it is ever worth versioning, the script
belongs next to these images and its `SHOTS` path needs updating to match.

## Not captured

Six figures in the guide remain labelled placeholders. Each needs either a real
submission to the production database or a deliberately broken condition (full
storage, server down, a stale observer). Nothing was submitted to production to
produce these. The guide states what each one needs.
