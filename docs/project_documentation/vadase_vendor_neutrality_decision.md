# Can `vadase-rt-monitor` accept any receiver? — a decision that needs making

**Written 2026-08-26**, prompted by a direct question: *"I expect the system to
parse input regardless of receiver (Trimble, Leica, etc.). Is the NTRIP / NMEA
expected stream the right choice?"*

**Status: DECISION REQUIRED.** This records what the service actually consumes,
why vendor-neutrality is not a parsing problem, and the three options — with a
recommendation, not a decision. The decision is PHIVOLCS'.

---

## First, the two words, because they are not alternatives

They belong to different layers. Asking "NTRIP or NMEA?" is like asking "HTTP
or JSON?" — you get one *inside* the other.

**NTRIP** — *Networked Transport of RTCM via Internet Protocol.* The **pipe**.
An HTTP/1.0-shaped protocol for streaming GNSS data over TCP: the client issues
`GET /MOUNTPOINT`, sends Basic auth, and the caster streams bytes indefinitely.
It does not care what those bytes are. A **mountpoint** is one named stream,
usually one receiver.

**NMEA 0183** — the **payload**. ASCII lines, comma-separated, one per line,
XOR checksum after the `*`:

```
$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
```

So the real choices are two independent ones:

| layer | options |
|---|---|
| **transport** | NTRIP · raw TCP · serial · file replay |
| **payload** | NMEA 0183 · RTCM 3 (binary; corrections and raw observations) · vendor binary (Trimble RT17, Leica LB2) |

`src/adapters/inputs/` already has `TCPAdapter` and `DirectoryAdapter` behind
the `InputPort` protocol, so **the transport layer is already vendor-neutral
and already pluggable.** That half of the question is answered and fine.

The payload is where the assumption breaks.

---

## What the parser actually accepts

`src/parsers/nmea_parser.py`, verified by reading the source rather than the
docstrings:

```python
if fields[0] not in ["$GNLVM", "$GPLVM"]:   # parse_lvm, line 119
if fields[0] not in ["$GNLDM", "$GPLDM"]:   # parse_ldm, line 174
```

Two sentence types, and **both are Leica proprietary**:

- `$GNLVM` — Leica **V**elocity **M**easurement
- `$GNLDM` — Leica **D**isplacement **M**easurement

Standard NMEA 0183 is `GGA`, `RMC`, `VTG`, `GSV` and friends. **`LVM` and `LDM`
are not in the standard.** A Trimble receiver will never emit them — not
because we cannot parse them, but because it does not produce them.

---

## The deeper reason this is not a parser problem

**VADASE is an algorithm, and Leica runs it on board.**

*Variometric Approach for Displacement Analysis Stand-alone Engine* — developed
at Sapienza University of Rome (Colosimo, Crespi, Mazzoni), licensed by Leica
and embedded in their receivers as an on-board option.

So this service **does not compute displacement.** It receives displacement a
Leica receiver already computed. That is not an implementation detail; it is
the premise the domain layer is built on. `ReceiverMode` — the state machine at
the centre of `domain/processor.py` — exists to decide **whether to trust the
receiver's own displacement or integrate the velocity ourselves**:

```python
class ReceiverMode(Enum):
    RECEIVER = auto()   # trust the receiver's LDM
    MANUAL   = auto()   # integrate LVM ourselves
```

That question only *has* meaning when the receiver is doing the science. Point
this service at a Trimble and there is nothing to parse and nothing to decide:
Trimble streams position and raw observations, and the variometric displacement
simply does not exist in that stream.

**Vendor-neutrality here is not a parsing gap. It is an algorithm we do not
have.**

---

## Three options

### 1. Multi-vendor at the payload layer

Add parsers for whatever other receivers emit.

**Does not achieve the goal.** There is no Trimble equivalent of `$GNLDM` to
parse. This buys position and raw-observation ingest — useful for other things,
not for real-time displacement.

*Effort: M. Achieves vendor-neutral displacement: no.*

### 2. Compute the variometric solution ourselves

Take raw observations — RTCM 3, or vendor binary — plus broadcast ephemeris,
and implement the variometric algorithm in `src/domain/`.

**This is the only option that actually satisfies "regardless of receiver",**
because every receiver streams raw observations. It is also, by a wide margin,
larger than everything currently in the service: carrier-phase handling, cycle
slips, ephemeris ingest, and a numerical result that must be validated against
Leica's on-board output before anyone trusts it in an earthquake response.

VADASE is published, so this is implementable rather than speculative. It is
research-grade work, not an afternoon.

*Effort: XL. Achieves vendor-neutral displacement: yes.*

### 3. Accept Leica-only for real time

Treat non-Leica CORS as post-processing sites, served by the Bernese chain, and
say so explicitly in the docs and the roadmap.

**Costs nothing and is honest.** It also matches what the network already is —
`CLAUDE.md` describes "35 VADASE-enabled CORS", which is a subset of the ~107
sites we hold data for, precisely because VADASE-enabled means Leica-with-the-
licence.

*Effort: S (documentation). Achieves vendor-neutral displacement: no, by
decision rather than by omission.*

---

## Recommendation

**Option 3 now; option 2 only if a specific need forces it.**

Reasons, in order of weight:

1. **Nothing is currently blocked by Leica-only.** The service does not yet run
   in production at all — see the deployment gaps below — so vendor-neutrality
   is not on the critical path to it working.
2. **Option 2 must be validated against option 3's output anyway.** The only
   credible way to trust our own variometric solution is to run it beside a
   Leica receiver and compare. So the Leica path has to work first regardless
   of which option is chosen.
3. **The requirement may dissolve on contact with the network.** If the
   non-Leica CORS are NAMRIA's (see `pagenet_namria_provenance.md`), the
   question is partly about data-sharing agreements rather than parsers.

What makes option 3 acceptable is writing it down. The current state is not
"we decided Leica-only" — it is that nothing says otherwise, so a reasonable
reader assumes the parser is the only obstacle.

---

## What this does not excuse

Vendor-neutrality is a *design* question. Separately, the service is **not
deployable today**, and those gaps are nearer-term:

| gap | evidence |
|---|---|
| `stations.yml` holds **4** stations, not 35 | `grep -c '^\s*- id:'` |
| every host is `192.168.1.10x` | the home-router default subnet; PHIVOLCS is `192.168.48.x` |
| **no NTRIP credentials** on any station | no `mountpoint`, `user` or `password` keys — and `TCPAdapter` deliberately does not retry on bad auth |
| the ingestor is **not a compose service** | root `docker-compose.yml` runs `db`, `redis`, `grafana` only |
| **nothing alerts** | `check_event_threshold` → `logger.warning` → a TimescaleDB row. No email, webhook or SMS anywhere in `src/` |
| no health or metrics endpoint | nothing reports that the ingestor is alive and stations are streaming |

The alerting gap is the one that matters most: for an earthquake-detection
system, a detection that reaches only a database and a log line is a detection
nobody sees. Grafana dashboards exist, but a dashboard is pull, not push.

---

## Documentation corrections this surfaced

- **`CLAUDE.md` says "Station definitions (35+)"** (lines 117 and 292).
  The file holds **4**, all on a placeholder subnet.
- **`CLAUDE.md` calls these "1 Hz VADASE NMEA streams"** without noting they
  are *Leica-proprietary sentences*. That omission is exactly what makes
  vendor-neutrality look like a parsing detail rather than an algorithm nobody
  has implemented here.
- **`roadmap.md` §6 lists VAD-001 and VAD-002 as remaining.** Both are done.
  The honest figure is **code ~95%, deployment ~0%** — not "~80% complete".

---

## The question to answer

**Is real-time displacement Leica-only by decision, or is vendor-neutral
displacement a requirement someone is expecting?**

If the second, it is option 2, and it should be scoped as a research
deliverable with its own timeline rather than as a parser enhancement. If the
first, three documentation edits close it and the service's real blockers are
the deployment gaps above.
