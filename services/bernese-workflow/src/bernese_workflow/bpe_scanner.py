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
  cause is the last error before the ERR line.
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

# " *** SR GTATML: TEXT", " ### PG ORBGEN (date)", " *** FN O_RNXBASE:rdHdrLine, PG CCRNXO".
# The emitter may be "MODULE:routine"; a colon followed by a space starts the text.
_HEADER = re.compile(
    r"^ ?(?P<mark>\*\*\*|###)\s+(?P<etype>SR|PGM|PG|FN)\s+"
    r"(?P<emitter>[A-Za-z0-9_]+(?::[A-Za-z0-9_]+)*)(?P<rest>.*)$"
)
_PROGRAM_SUFFIX = re.compile(r"^,\s*PG\s+(?P<program>[A-Za-z0-9_]+)")
# Continuation lines are indented; the protocol's own MSG/ERR lines have one space.
_DETAIL = re.compile(r"^\s{2,}\S")
# " 30-SEP-2026  16:22:37  00:00:03  00:00:02  ERR GPSEST    ERROR IN MAIN PROGRAM"
_PRT_ERR = re.compile(r"^\s*\d{2}-[A-Z]{3}-\d{4}(?:\s+\d{2}:\d{2}:\d{2})+\s+ERR\s+(\S+)")
_LOG_ERR = re.compile(r"^Call to (\S+) failed:")
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


def scan(text: str) -> StepReport:
    """Scan one step's PRT or LOG text."""
    lines = text.splitlines()
    messages: list[BernMessage] = []
    failed_program: str | None = None
    err_line: int | None = None

    i = 0
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
            elif e := _LOG_ERR.match(lines[i]):
                # The LOG prints this marker before the messages, so it bounds nothing.
                failed_program = e[1]
        i += 1

    cause = None
    if failed_program is not None:
        before = [
            msg
            for msg in messages
            if msg.severity == "error" and (err_line is None or msg.line < err_line)
        ]
        cause = before[-1] if before else None
    return StepReport(tuple(messages), failed_program, cause)


def scan_file(path: Path) -> StepReport:
    return scan(path.read_text(encoding="utf-8", errors="replace"))
