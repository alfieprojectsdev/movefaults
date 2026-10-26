"""
Scan BPE step output for Bernese error and warning messages.

This is step 1 of the decision layer in
``docs/project_documentation/bpe_orchestration_design.md``: turn a step's
``.PRT`` protocol or ``.LOG`` into typed records, so that a knowledge base can
map a failure to a diagnosis and a circuit breaker can count repeats of one
failure instead of counting failed days.

The format is AIUB's own contract (DOCU52 section 21.7): an error starts with
``***`` and a warning with ``###``. A message is one header line followed by
indented continuation lines, with no nesting, so this is a line scanner, not a
parser::

     *** SR GTATML: ATMOSPHERIC TIDAL LOADING CORRECTION VALUES NOT FOUND
                    RETURN CODE  :  2
                    STATION NAME : PTAG 22006M005
                    FILE NAME    : ${P}/PHD252000/STA/PHDEN.ATL

becomes ``signature == ("GTATML", "ATMOSPHERIC_TIDAL_LOADING_CORRECTION_VALUES_NOT_FOUND")``
with the three continuation lines as ``params``.

Two things the obvious approach gets wrong, both seen in captured output:

- **An error message is not a failure.** CCRNXO writes ``*** FN
  O_RNXBASE:rdHdrLine`` for each empty RINEX file it skips and then ends
  normally. Whether the step failed comes from the failure marker -- the PRT's
  ``ERR <program>`` line, or the LOG's ``Call to <program> failed:`` -- and the
  cause is the last error the failed program printed: in a PRT, after its
  ``MSG <program> PROGRAM STARTED`` line and before its ERR line; in a LOG,
  after the marker. A step can run several programs, and an error an earlier
  one printed and survived is not the failure.
- **Data belongs in params, not in the signature.** neqckdim reports the
  first parameter request that overflowed; the same misconfiguration gives a
  different number on every day, and many warnings name a station or baseline
  in their text. ``kind`` drops numbers, quoted strings and parenthesised
  groups so that 24 failures of one cause share one signature. The numbers are kept raw, as
  strings, in ``params``: what they mean is the knowledge base's job.

A failed step with no ``***`` message (a Perl-level failure) has ``cause``
``None``. That is "unknown", and the caller must treat it as such.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Severity = Literal["error", "warning"]

# The emitter may be "MODULE:routine"; a colon followed by a space starts the text.
EMITTER = r"[A-Za-z0-9_]+(?::[A-Za-z0-9_]+)*"
# " *** SR GTATML: TEXT", " ### PG ORBGEN (date)", " *** FN O_RNXBASE:rdHdrLine, PG CCRNXO".
_HEADER = re.compile(
    r"^ ?(?P<mark>\*\*\*|###)\s+(?P<etype>SR|PGM|PG|FN)\s+"
    rf"(?P<emitter>{EMITTER})(?P<rest>.*)$"
)
_PROGRAM_SUFFIX = re.compile(r"^,\s*PG\s+(?P<program>[A-Za-z0-9_]+)")
# Continuation lines are indented; the protocol's own MSG/ERR lines have one space.
_DETAIL = re.compile(r"^\s{2,}\S")
# " 30-SEP-2026  16:22:37  00:00:03  00:00:02  ERR GPSEST    ERROR IN MAIN PROGRAM"
_PRT_ERR = re.compile(r"^\s*\d{2}-[A-Z]{3}-\d{4}(?:\s+\d{2}:\d{2}:\d{2})+\s+ERR\s+(\S+)")
_LOG_ERR = re.compile(r"^Call to (\S+) failed:")
# " 30-SEP-2026  16:22:35  00:00:01            MSG GPSEST    PROGRAM STARTED"
_PRT_START = re.compile(
    r"^\s*\d{2}-[A-Z]{3}-\d{4}(?:\s+\d{2}:\d{2}:\d{2})+\s+MSG\s+(\S+)\s+PROGRAM STARTED"
)
# Where an attempt starts. Nothing removes a step's PRT or LOG between attempts:
# writePrtFileHeader appends (``>>``), and so does USER.CPU's ``>> <LOG>``. A rerun
# of the same session in the same campaign leaves every earlier attempt above the
# current one. The PRT header opens each attempt's PRT. RUNBPE.pm prints
# ``Perl version:`` at top level, before START, so it opens each attempt's LOG even
# when the script fails to compile; LOGFILE_HEADER (START only) is the fallback.
_ATTEMPT = re.compile(r"^(?:\s*PROTOCOL FILE FOR BPE SCRIPT\s*|Perl version:.*)$")
_LOG_HEADER = re.compile(r"^LOGFILE_HEADER\s*$")
_NUMBER = re.compile(r"(?<![A-Za-z0-9_.])[-+]?\d+(?:\.\d+)?(?![A-Za-z0-9_])")
# Where messages put data rather than words: "ALAB ALAB", (HERT-WSRT), (G049).
_QUOTED = re.compile(r'"[^"]*"')
_PARENS = re.compile(r"\([^()]*\)")
_PARAM = re.compile(r"^(?P<key>[A-Za-z][^:]*?)\s*:\s*(?P<value>.*?)\s*$")


@dataclass(frozen=True)
class BernMessage:
    severity: Severity
    emitter_type: str  # SR subroutine, PG/PGM program, FN function
    emitter: str  # as printed, case kept: "neqckdim", "D_STACRX:chkType002"
    program: str | None  # from a PG/PGM header or a ", PG X" suffix
    headline: str  # text after "EMITTER:", "" when the header has none
    kind: str  # headline (or first detail line) canonicalised, see kind_of
    detail: tuple[str, ...]  # continuation lines, stripped
    params: dict[str, str] = field(default_factory=dict)
    line: int = 0  # 1-based line of the header

    @property
    def signature(self) -> tuple[str, str]:
        """The deduplication key the knowledge base and the breaker match on."""
        return (self.emitter, self.kind)


@dataclass(frozen=True)
class StepReport:
    messages: tuple[BernMessage, ...]
    failed_program: str | None
    cause: BernMessage | None

    @property
    def failed(self) -> bool:
        return self.failed_program is not None


def kind_of(text: str) -> str:
    """Canonical message kind: text before its first colon, data dropped.

    Numbers, double-quoted strings and parenthesised groups are removed, because
    that is where Bernese prints station names, baselines and satellites:
    ``"16 OF 16 SATELLITES WITH DATA PROBLEMS AT EPOCH 1914 (HERT-WSRT)"`` ->
    ``"OF_SATELLITES_WITH_DATA_PROBLEMS_AT_EPOCH"``. Single-quoted text is kept;
    there it names a category (``'New site occupation event'``).
    """
    text = text.split(":", 1)[0]
    for pattern in (_QUOTED, _PARENS, _NUMBER):
        text = pattern.sub(" ", text)
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def _param_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _message(m: re.Match[str], detail: list[str], line: int) -> BernMessage:
    rest = m["rest"]
    program = m["emitter"] if m["etype"] in ("PG", "PGM") else None
    if suffix := _PROGRAM_SUFFIX.match(rest):
        program = suffix["program"]
        rest = rest[suffix.end() :]
    headline = rest.split(":", 1)[1].strip() if rest.lstrip().startswith(":") else ""

    params: dict[str, str] = {}
    for d in detail:
        if p := _PARAM.match(d):
            params.setdefault(_param_key(p["key"]), p["value"])

    kind = kind_of(headline) or (kind_of(detail[0]) if detail else "")
    return BernMessage(
        severity="error" if m["mark"] == "***" else "warning",
        emitter_type=m["etype"],
        emitter=m["emitter"],
        program=program,
        headline=headline,
        kind=kind,
        detail=tuple(detail),
        params=params,
        line=line,
    )


def _last(lines: list[str], pattern: re.Pattern[str]) -> int | None:
    return max((n for n, line in enumerate(lines) if pattern.match(line)), default=None)


def scan(text: str) -> StepReport:
    """Scan one step's PRT or LOG text."""
    lines = text.splitlines()
    messages: list[BernMessage] = []
    failed_program: str | None = None
    err_line: int | None = None
    # Messages at or before this line belong to an earlier program, not the failed one.
    start_line = 0
    starts: list[tuple[int, str]] = []

    # Only the last attempt counts. Line numbers stay those of the whole file.
    i = _last(lines, _ATTEMPT)
    if i is None:
        i = _last(lines, _LOG_HEADER) or 0
    while i < len(lines):
        if m := _HEADER.match(lines[i]):
            start = i
            i += 1
            detail = []
            while i < len(lines) and _DETAIL.match(lines[i]) and not _HEADER.match(lines[i]):
                detail.append(lines[i].strip())
                i += 1
            messages.append(_message(m, detail, start + 1))
            continue
        if failed_program is None:
            if e := _PRT_ERR.match(lines[i]):
                failed_program, err_line = e[1], i + 1
                start_line = max((n for n, p in starts if p == failed_program), default=0)
            elif e := _LOG_ERR.match(lines[i]):
                # The LOG prints this marker before the failed program's messages.
                failed_program, start_line = e[1], i + 1
            elif s := _PRT_START.match(lines[i]):
                starts.append((i + 1, s[1]))
        i += 1

    cause = None
    if failed_program is not None:
        own = [
            msg
            for msg in messages
            if msg.severity == "error"
            and msg.line > start_line
            and (err_line is None or msg.line < err_line)
        ]
        cause = own[-1] if own else None
    return StepReport(tuple(messages), failed_program, cause)


def scan_file(path: Path) -> StepReport:
    return scan(path.read_text(encoding="utf-8", errors="replace"))
