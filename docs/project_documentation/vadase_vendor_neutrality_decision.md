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
| **unrecognised sentences are dropped silently** | `process_sentence` is `if`/`elif` with no `else` — a misconfigured receiver looks exactly like a dead one. See the NetR9 section below |

The alerting gap is the one that matters most: for an earthquake-detection
system, a detection that reaches only a database and a log line is a detection
nobody sees. Grafana dashboards exist, but a dashboard is pull, not push.

---

## A worked example: could it show a Trimble NetR9 at all?

Asked directly — *"assuming all the credentials are ready, can it at minimum
display incoming Trimble NetR9 streams, e.g. live position data?"* The answer
is **no**, and tracing why is more useful than the answer, because the first
reason is a defect that bites Leica too.

### 1. Unrecognised sentences are dropped in silence

`domain/processor.py:124-133`:

```python
async def process_sentence(self, sentence: str):
    try:
        if sentence.startswith('$GNLVM') or sentence.startswith('$GPLVM'):
            await self.handle_velocity(sentence)
        elif sentence.startswith('$GNLDM') or sentence.startswith('$GPLDM'):
            await self.handle_displacement(sentence)
    except NMEAChecksumError:
        ...
```

**`if` / `elif`, and no `else`.** A `$GPGGA` position sentence hits neither
branch, falls off the end and is discarded — no log line, no counter, no
warning. The connection stays healthy, the dashboard stays empty, and nothing
anywhere says why.

**This is not a Trimble problem.** A *Leica* receiver misconfigured to emit
`GGA` instead of `LVM` produces exactly the same picture: a live TCP session,
bytes arriving, and no data. Today that is indistinguishable from a dead
station.

**It is worth fixing regardless of which option below is chosen** — an `else`
that counts unrecognised sentence types by prefix and logs them periodically.
Small, and it converts the commonest misconfiguration from silent to obvious.

### 2. The NetR9's default output is probably not ASCII at all

Trimble receivers default to **RT17/RT27 or RTCM 3** — binary. The adapter does
`data.decode('ascii', errors='ignore')` and splits on `\n`
(`adapters/inputs/tcp.py:79-89`), so binary input becomes mangled fragments cut
on stray `0x0A` bytes, each then silently dropped by (1).

A NetR9 *can* be configured to emit NMEA on a port. That is a receiver-side
setting, not a code change — worth knowing, because it means this particular
obstacle costs nothing to remove.

### 3. There is no display path even for a sentence we do parse

`write_event_detection` fires only above threshold. Nothing serves "current
position", and the Grafana dashboards read tables the ingestor writes on
detections and processed epochs. A parsed `GGA` would have nowhere to go.

### What "minimum viable NetR9 visibility" would cost

Roughly half a day, and it does **not** require answering the vendor-neutrality
question:

| piece | note |
|---|---|
| `else` branch counting unrecognised sentences | worth doing regardless; see above |
| `parse_gga` for position | standard NMEA, unlike `LVM`/`LDM` |
| a passthrough output port | so a parsed position reaches somewhere visible |

That yields *position*, not displacement. **Displacement from a NetR9 is
option 2 and nothing less** — the receiver does not compute a variometric
solution, so there is nothing to receive.

### What this confirms about the architecture

Parsing lives in the **domain** layer, not the adapter. `TCPAdapter` frames
lines on `\n` and hands strings on; it has never known what a Leica sentence
is. So supporting another payload touches `parsers/` and `domain/`, and leaves
the transport alone — which is the hexagonal boundary working as intended, and
the reason none of the above is expensive.

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
