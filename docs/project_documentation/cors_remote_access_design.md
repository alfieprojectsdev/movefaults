# Remote access to CORS receivers over mobile data

**Drafted 2026-09-05, gps3.** Speculative design note, not a decision. Written
in response to standing advice that nationwide remote access to CORS receivers
"is only possible with industrial-grade routers", the alternative being
carrier-issued public IP addresses that do not scale to hundreds of stations at
any realistic budget.

**Status: proposal.** Nothing here has been tested against a real station on a
real SIM. Section 9 says what would settle it. Do not cite this as established.

---

## 1. The reframing

The advice and the counter-advice are arguing about the wrong thing. The
question is not *"how do we reach into a station behind CGNAT"*. It is
*"which of the things we want actually requires reaching in?"*

Three separate jobs get bundled together as "remote access", and they have
different answers:

| Job | Direction it naturally flows | Needs inbound reach? |
|---|---|---|
| **Real-time stream** (RTCM corrections, VADASE NMEA) | station → centre | **No** — if the receiver pushes |
| **Daily file retrieval** (RINEX for Bernese) | station → centre | **No** — if the station pushes |
| **Management** (web UI, firmware, config, diagnosis) | centre → station | **Yes**. Irreducibly. |

The first two are the *bulk* of the value and **do not need a VPN at all**.
The third genuinely does, and is where an overlay network earns its place.

Collapsing all three into one problem is what makes the answer look like
"buy hundreds of industrial routers" or "buy hundreds of public IPs". Neither
is necessary for jobs 1 and 2, and job 3 needs neither.

## 2. Why jobs 1 and 2 do not need inbound reach

NTRIP already solved this, and it is the reason the protocol is shaped the way
it is. The caster is the only component that must be publicly reachable;
NTRIP **servers** (the stations) and NTRIP **clients** (consumers) both open
*outbound* connections to it. CGNAT does not obstruct outbound connections.

**One public IP for the whole national network**, at the caster. Not one per
station.

This is not a workaround. It is how essentially every national CORS network
and every commercial RTK service is built, and the reason casters exist as a
distinct role in the standard.

### Our receivers can do this today

The Leica GR30/GR50 datasheet lists **NTRIP server (source), client and caster**
functionality, with unlimited mount points. All three roles, selectable.

`docs/project_documentation/ticket_backlog.md` VAD-002 records that we
currently use the **embedded caster** — the receiver *is* the caster, so the
centre must dial in to `192.168.1.10x:5017`. `stations.yml` confirms it: LAN
addresses, port 5017, no `mountpoint` set on any production station.

**That configuration choice, not CGNAT, is what makes our stations
unreachable over cellular.** It is fine on a LAN and fatal over mobile data.
Switching a station from "local caster" to an external caster address is a
receiver configuration change, not a hardware purchase.

### Our own code is already on the right side of this

`services/vadase-rt-monitor/src/adapters/inputs/tcp.py` implements
`_perform_handshake()` — `GET /<mountpoint> HTTP/1.0`, validate `ICY 200 OK`,
drain headers. **`TCPAdapter` is already an NTRIP client.** VAD-002 built it.

Pointing it at a central caster instead of at 35 individual receivers is a
config change (`host`/`port`/`mountpoint` in `stations.yml`), not a rewrite.
It would also collapse 35 outbound connections from gps3 into one destination,
which removes the reconnect-stampede problem the code currently works around
with jittered backoff.

### Daily files for Bernese are cheaper still

The post-processing path needs one ~1.5–4 MB Hatanaka-compressed daily file
per station per day *(estimate; measure ours before quoting it)*. That is a
push — `rsync`/`scp`/FTP out of the station on a cron — and needs no inbound
reach either. Today those files reach us via the Windows file server at
`192.168.48.99` over SMB, which is the same pattern with a different transport.

## 3. Where Tailscale is genuinely the right tool

Job 3. Interactive management: the receiver's web UI, firmware updates,
configuration changes, and — the one that actually matters at 03:00 after an
event — **diagnosing a station that has stopped sending**.

You cannot push your way out of "why did it stop". That needs a live inbound
session, and that is exactly what CGNAT denies.

The mechanism Gemini describes is correct:

- the station's **gateway** (not the receiver) joins the tailnet with an
  outbound connection, which CGNAT permits;
- **subnet routing** exposes the receiver's LAN address (`192.168.8.100`) to
  the centre, so the receiver itself needs no software and no firmware support;
- the station gets a stable `100.x.x.x` address that survives the carrier
  reassigning its real IP.

That third point is worth more than it looks. It means station identity stops
being a network property. `stations.yml` could carry permanent addresses
instead of LAN addresses that only mean anything inside one building.

## 4. The cost claim is wrong, and wrong in the direction that matters

Gemini said "₱0 — free for up to 3 users and 100 devices". That misreads
Tailscale's billing unit in exactly the case we are asking about.

Tailscale distinguishes **user devices** (a person's laptop and phone; these
share one seat and are effectively free) from **tagged resources** — "a device
owned by a tag rather than a user identity… servers, subnet routers, app
connectors, and other shared infrastructure."

**A CORS station gateway is a tagged resource.** It is unattended
infrastructure with no human owner. It is precisely the billable unit.

Published allowances at time of writing:

| Plan | Price | Tagged resources |
|---|---|---|
| Personal | free | 50 included, then **$1/month each** |
| Standard | $8/user/mo | not published — "contact sales" |
| Premium | $18/user/mo | not published — "contact sales" |
| Enterprise | custom | custom |

So a 100-station network is roughly **$50/month**, not ₱0, and a 400-station
network is not quoted publicly at all. Tailscale states it is **not currently
enforcing** tagged-resource limits but intends to begin. Building a national
network on an unenforced limit is building on an announced future bill.

**This is still dramatically cheaper than per-station public IPs.** The
correction is not "Tailscale is expensive". It is that the number is not zero,
is not published at our scale, and is a recurring foreign-currency SaaS
subscription — which for a government agency is a procurement instrument that
may be harder to obtain than a one-off capital purchase, independent of size.
That constraint should be checked with PHIVOLCS finance *before* the technical
pilot, because it can invalidate the whole approach for non-technical reasons.

## 5. Headscale: the escape from both problems

[Headscale](https://github.com/juanfont/headscale) is an open-source
reimplementation of Tailscale's coordination server. Same clients, same
WireGuard data plane, control plane on your own hardware.

For national monitoring infrastructure this is arguably a requirement rather
than an optimisation:

- **no per-device billing** — the tagged-resource question disappears;
- **no foreign dependency** in the control path for seismic monitoring;
- **no recurring subscription** to defend at each budget cycle.

Honest costs, from the same sources:

- community-maintained; narrower scope than the commercial product;
- YAML configuration, no polished admin UI;
- reduced MagicDNS; Funnel unsupported (we need neither);
- **you must run your own DERP relay** for the cases where a direct
  peer-to-peer connection cannot be established. This is the operationally
  serious one — see §7.

A reasonable sequencing: **pilot on Tailscale** (fastest path to an answer,
free at pilot scale), **migrate to Headscale before national rollout**. The
clients are identical, so the pilot's findings transfer.

## 6. The "industrial router" advice deserves a better hearing

Gemini called it "outdated" because it answered the addressing problem with
hardware. That is too glib, and dismissing it wholesale would be an expensive
mistake.

The likely real reason for the recommendation is **environmental survival, not
IP addressing**:

- operating range well beyond a consumer router's 0–40 °C in an unventilated
  roadside or summit enclosure;
- **surge and lightning protection** — the Philippines is among the most
  lightning-exposed countries on earth, and a CORS site is a grounded mast;
- **hardware watchdog with automatic reboot** on hang;
- dual-SIM failover where one carrier has no coverage;
- 9–36 V DC input, because sites run on solar and battery, not mains;
- DIN-rail mounting and a supply chain that still stocks the part in five years.

**Both pieces of advice are right about different things.** Gemini is right
that you do not need industrial hardware to solve *addressing*. The advisor is
right that you need it to survive *the site*. The synthesis is: adopt the
overlay network to kill the public-IP cost, and keep spending on ruggedised
hardware where the environment demands it — now justified on its own merits
rather than as a workaround for addressing.

### We already have the counter-example in the building

`finch` — the T420 in the PHIVOLCS cubicle — "occasionally hangs and needs a
restart", and this week that meant work stalled because nobody could physically
reach it. That is one machine, indoors, air-conditioned, with a person in the
same building.

Multiply that failure mode by hundreds of unattended enclosures on mountains,
and a station you cannot power-cycle is a station you have lost until someone
drives to it. **A watchdog that reboots on hang is worth more than any amount
of remote access software**, because remote access presupposes the box is still
answering. `docs/finch/HEADLESS_HARDENING_PLAYBOOK.md` (PR #170) is the same
lesson at n=1.

## 7. Operational traps neither answer mentioned

1. **Key expiry will take down the entire network on a timer.** Tailscale
   devices re-authenticate periodically (90 days by default). An unattended
   field gateway cannot complete an interactive re-auth. Every station must be
   provisioned with key expiry **disabled**, or with a non-expiring auth key,
   or the network dies station-by-station three months after rollout with no
   triggering event. This is the single most likely way to get badly burned.

2. **The tailnet is one blast radius.** Compromise of the coordination account
   is access to every station. This needs ACL design — tag-scoped, deny by
   default, management access from named operator devices only — before
   rollout, not after. For national infrastructure this is also a policy
   question, not only a technical one.

3. **Not every link will be peer-to-peer.** Two endpoints both behind CGNAT
   may fail to hole-punch and fall back to a DERP relay. Traffic stays
   end-to-end encrypted, so this is a latency and availability concern, not a
   confidentiality one — but for a real-time seismic stream the latency matters,
   and on Headscale *you* own the relay's uptime.

4. **Mobile data volume is the recurring cost nobody costed.** Rough
   order-of-magnitude, to be measured not trusted:

   | Stream | Est. rate | Est. per station/month |
   |---|---|---|
   | RTCM3 corrections, multi-GNSS 1 Hz | ~2–6 kbit/s | ~1–3 GB |
   | Raw observations 1 Hz | ~10–20 kbit/s | ~3–6 GB |
   | VADASE NMEA (LVM+LDM) 1 Hz | ~1.5 kbit/s | ~0.4 GB |
   | Daily RINEX file only | — | **~0.1 GB** |

   At hundreds of stations the SIM plans plausibly **dominate** both the
   hardware and the Tailscale line. It is also the strongest argument for
   separating the planes: if a site does not need a real-time stream, daily
   file push costs about 3 % of what streaming costs.

## 8. What this would change in our codebase

Nothing urgent, and nothing that should be built before §9 answers the
question. Recorded so the shape is known:

- `stations.yml` gains `mountpoint` per station and points at one caster host
  rather than 35 LAN addresses;
- `TCPAdapter`'s reconnect jitter becomes less load-bearing (one destination);
- station identity in config becomes a stable overlay address or a mountpoint
  name, not a LAN IP;
- **stale-doc note:** `CLAUDE.md` claims "35+ CORS stations" and
  `config/stations.yml` defines **4**. One of the two is wrong. Found while
  writing this; consistent with the `stale_doc_audit.md` findings.

## 9. What would actually settle this

A single-station pilot answers nearly everything, cheaply:

1. One station, one SIM, one cheap Tailscale-capable gateway.
2. **Reconfigure the receiver from embedded caster to external NTRIP server**
   pointing at a caster we run. Confirm the stream arrives with no VPN at all.
   *This step alone may make the rest unnecessary for jobs 1 and 2.*
3. Bring the gateway onto a tailnet, enable subnet routing, confirm the
   receiver web UI is reachable from gps3.
4. Leave it for **90+ days untouched** — the only way to find out whether key
   expiry, carrier idle-timeouts, or the enclosure kill it. A pilot shorter
   than the key expiry window does not test the thing most likely to fail.
5. Measure actual data volume against the §7 estimates.
6. Confirm with finance whether a recurring USD subscription is procurable at
   all; if not, Headscale is not an option but a precondition.

## Open questions

- Which carriers have coverage at the existing station sites? This constrains
  hardware (dual-SIM) more than anything above.
- Do the current sites have power budget for a gateway alongside the receiver?
- Is there an existing PHIVOLCS or NAMRIA caster we should feed rather than
  standing up our own? PAGENET is NAMRIA's, and duplicating national
  infrastructure would be worth avoiding.
- Does anything in the DOST/agency security policy prohibit a third-party
  coordination server in the path? If so, §5 is decided for us.

## Sources

- Tailscale pricing and tagged-resource definition — <https://tailscale.com/pricing>
- Tailscale tags — <https://tailscale.com/docs/features/tags>
- Headscale — <https://github.com/juanfont/headscale>
- Leica GR30/GR50 datasheet (NTRIP server/client/caster) —
  <https://leica-geosystems.com/en-gb/products/gnss-reference-networks/receivers/leica-gr50-and-gr30>
- NTRIP caster role and firewall traversal — <https://www.use-snip.com/kb/knowledge-base/question-what-is-an-ntrip-caster/>

Prices and plan limits were read on 2026-09-05 and are the most perishable
content in this document. Re-check before quoting them in a procurement paper.
