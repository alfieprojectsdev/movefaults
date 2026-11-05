"""Where the console looks, read once at start-up.

Every path comes from the same place the processing service gets it: the
BSW variables LOADGPS.setvar exports ($U, $D, $S, $P). The console never takes
a path from the browser; a request names a campaign, a year and a day, and the
server turns those into paths from here.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_EXPORT = re.compile(r'^\s*export\s+([A-Z_][A-Z0-9_]*)="?([^"#]*?)"?\s*(?:#.*)?$')
_REF = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def read_setvar(path: Path, env: dict[str, str] | None = None) -> dict[str, str]:
    """The `export NAME="value"` lines of LOADGPS.setvar, with ${VAR} expanded.

    Only plain assignments are read; anything the shell would compute is left
    alone. Unknown references expand to "" as the shell would.
    """
    out: dict[str, str] = {}
    scope = dict(os.environ if env is None else env)
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        m = _EXPORT.match(line)
        if not m:
            continue
        value = _REF.sub(lambda r: scope.get(r[1] or r[2], ""), m[2].strip())
        scope[m[1]] = value
        out[m[1]] = value
    return out


@dataclass(frozen=True)
class Campaign:
    """A campaign the console shows: its daily PCF and its per-day campaign prefix.

    ``float_pcf`` is the PCF a day falls back to when its fixed solution fails
    its checks; days solved only there are shown as float. Its results go to a
    different SAVEDISK directory, so the two never mix.
    """

    name: str
    pcf: str
    prefix: str = ""
    float_pcf: str = ""


def parse_campaigns(spec: str) -> list[Campaign]:
    """``NAME:PCF[:PREFIX[:FLOAT_PCF]]``, comma-separated."""
    out = []
    for item in spec.split(","):
        parts = [p.strip() for p in item.split(":")]
        if not parts[0]:
            continue
        parts += [""] * (4 - len(parts))
        out.append(
            Campaign(
                parts[0].upper(), parts[1] or f"{parts[0].upper()}_DLY", parts[2].upper(), parts[3]
            )
        )
    return out


DEFAULT_CAMPAIGNS = "LUZON:LUZON_DLY:LZY:LZFLT_DLY,PHREF:PHREF_DLY:PHR,PHDEN:PHDEN_DLY:PHD"


@dataclass
class Settings:
    gpsuser: Path  # $U
    datapool: Path  # $D
    savedisk: Path  # $S
    campaigns_dir: Path  # $P
    campaigns: list[Campaign]
    kb_path: Path | None = None  # None: bernese_workflow's own default
    lock_path: Path | None = None  # None: bernese_workflow's own default
    state_dir: Path = field(default_factory=lambda: Path.home() / ".local/state/bsw-console")
    static_dir: Path | None = None
    # Stage 3 actions (start, stop, redo, preflight) queue requests for the run
    # worker (bernese-worker). Off unless BSW_CONSOLE_ACTIONS=on; while off the
    # endpoints answer 501 and say why. See bsw_console/actions.py.
    actions_enabled: bool = False
    # The run worker's queue: the same directory `bernese-worker run` reads.
    # None: bernese_workflow.run_queue's default ($BERNESE_WORKER_STATE or
    # ~/.local/state/bernese-workflow/worker).
    worker_state: Path | None = None
    # Signed-in users who may press the stage 3 buttons. Empty: nobody, even
    # with actions on; the list has to be set on purpose.
    operators: frozenset[str] = frozenset()
    # Addresses of reverse proxies allowed to name the signed-in user in
    # X-Remote-User. Empty (the default): the header is ignored from everyone,
    # because without a proxy any client on the network could send it.
    trusted_proxies: frozenset[str] = frozenset()
    # The time series (stage 5) reads each campaign year's daily final CRDs
    # from that year's result directory (<V_RESULT>/STA, as the PCF sets it),
    # so the page shows the campaign and year it names. BSW_CONSOLE_TS_OFFSETS
    # (the offsets catalog) has no default: unset, the page says the time
    # series is not configured. The reference station is chosen on the page;
    # BSW_CONSOLE_TS_REFERENCE is only the one it starts with, and may be unset.
    ts_reference: str | None = None
    ts_offsets: Path | None = None
    # The JSON `bernese-check-equipment --json` wrote (BSW_CONSOLE_EQUIPMENT_REPORT).
    # None: the station view says there is no equipment report.
    equipment_report: Path | None = None

    @property
    def env(self) -> dict[str, str]:
        """The BSW variables, as bernese_workflow.run_plan expects them."""
        return {
            "U": str(self.gpsuser),
            "D": str(self.datapool),
            "S": str(self.savedisk),
            "P": str(self.campaigns_dir),
        }

    def campaign(self, name: str) -> Campaign:
        for c in self.campaigns:
            if c.name == name.upper():
                return c
        raise KeyError(name)

    @classmethod
    def from_env(cls) -> Settings:
        setvar = Path(os.environ.get("BSW_SETVAR", Path.home() / "BERN54" / "LOADGPS.setvar"))
        bsw = read_setvar(setvar)

        def var(name: str, default: Path) -> Path:
            return Path(os.environ.get(name) or bsw.get(name) or default)

        home = Path.home()
        here = Path(__file__).resolve().parents[2]
        static = Path(os.environ.get("BSW_CONSOLE_STATIC", here / "frontend" / "dist"))
        kb = os.environ.get("BSW_CONSOLE_KB")
        lock = os.environ.get("BPE_LOCK")
        ts_ref = os.environ.get("BSW_CONSOLE_TS_REFERENCE")
        ts_off = os.environ.get("BSW_CONSOLE_TS_OFFSETS")
        report = os.environ.get("BSW_CONSOLE_EQUIPMENT_REPORT")
        return cls(
            gpsuser=var("U", home / "GPSUSER"),
            datapool=var("D", home / "GPSDATA" / "DATAPOOL"),
            savedisk=var("S", home / "GPSDATA" / "SAVEDISK"),
            campaigns_dir=var("P", home / "GPSDATA" / "CAMPAIGN54"),
            campaigns=parse_campaigns(os.environ.get("BSW_CONSOLE_CAMPAIGNS", DEFAULT_CAMPAIGNS)),
            kb_path=Path(kb) if kb else None,
            lock_path=Path(lock) if lock else None,
            ts_reference=ts_ref.strip().upper() if ts_ref and ts_ref.strip() else None,
            ts_offsets=Path(ts_off) if ts_off else None,
            equipment_report=Path(report) if report else None,
            state_dir=Path(os.environ.get("BSW_CONSOLE_STATE", home / ".local/state/bsw-console")),
            static_dir=static if static.is_dir() else None,
            actions_enabled=os.environ.get("BSW_CONSOLE_ACTIONS", "").strip().lower() == "on",
            worker_state=Path(ws) if (ws := os.environ.get("BERNESE_WORKER_STATE")) else None,
            operators=frozenset(
                x.strip()
                for x in os.environ.get("BSW_CONSOLE_OPERATORS", "").split(",")
                if x.strip()
            ),
            trusted_proxies=frozenset(
                x.strip()
                for x in os.environ.get("BSW_CONSOLE_TRUSTED_PROXIES", "").split(",")
                if x.strip()
            ),
        )
