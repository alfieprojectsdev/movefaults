"""
Look up a BPE failure in the knowledge base, ``config/bernese/bpe_errors.yaml``.

Step 2 of the decision layer in
``docs/project_documentation/bpe_orchestration_design.md``. The scanner
(``bpe_scanner``) names a failure; this says what it means here and what to do,
from a file that people who are not programmers can extend. The diagnosis lives
in that file, not in this code and not in a session log.

Rules this module keeps:

- **Unknown is not guessed.** ``lookup`` returns ``None`` for an error with no
  row, and the caller must halt and show the raw message. There is no default
  remedy.
- **Nothing is applied.** A row is text for a person. ``scope`` is the only
  field code acts on: ``configuration`` stops a run at once, ``session`` lets
  the circuit breaker count repeats.
- **A bad edit fails loudly.** The file is validated as a whole on load, and
  every complaint names the entry and the field, because the person reading it
  edited a YAML file, not this module.

A row matches on the emitter (case-insensitive) and on ``kind_of(message)``,
the same canonical form the scanner gives the message, so the text can be
pasted from a ``.PRT`` as printed.

Run ``python -m bernese_workflow.bpe_knowledge FILE.PRT ...`` to see what the
table says about a step. Exit status: 0 when every failed step has a row, 1
when one does not, 2 when the knowledge base itself is invalid.
"""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import yaml

from bernese_workflow.bpe_scanner import EMITTER, BernMessage, StepReport, kind_of, scan_file

# src/bernese_workflow/ -> src -> bernese-workflow -> services -> repo root
DEFAULT_PATH = Path(__file__).resolve().parents[4] / "config" / "bernese" / "bpe_errors.yaml"

SCOPES = ("configuration", "session")
STATUSES = ("established", "proposed")
_REQUIRED = ("emitter", "message", "scope", "status", "diagnosis", "remedy", "source")
_OPTIONAL = ("confirm",)


class KnowledgeBaseError(ValueError):
    """The knowledge base file is invalid. The message says where and why."""


def match_key(message: BernMessage) -> tuple[str, str]:
    """What a row matches on: the emitter in any case, and the message's kind."""
    return (message.emitter.lower(), message.kind)


class _Loader(yaml.SafeLoader):
    """safe_load, except that a field given twice in one entry is an error.

    Plain YAML keeps the last of the two and drops the first without a word.
    """


def _mapping(loader: _Loader, node: yaml.MappingNode, deep: bool = False) -> dict:
    # Compared as written: as values, 1 and `yes` (True) would collide.
    seen: set[str] = set()
    for key_node, _ in node.value:
        if not isinstance(key_node, yaml.ScalarNode):
            continue
        if key_node.value in seen:
            raise KnowledgeBaseError(
                f"line {key_node.start_mark.line + 1}: '{key_node.value}' is given twice "
                "in one entry; keep one"
            )
        seen.add(key_node.value)
    return loader.construct_mapping(node, deep=deep)


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@dataclass(frozen=True)
class Entry:
    emitter: str
    message: str
    kind: str
    scope: str
    status: str
    diagnosis: str
    remedy: str
    source: str
    confirm: str | None
    number: int  # 1-based position in the file, for messages

    @property
    def key(self) -> tuple[str, str]:
        return (self.emitter.lower(), self.kind)


@dataclass(frozen=True)
class KnowledgeBase:
    entries: tuple[Entry, ...]

    def lookup(self, message: BernMessage) -> Entry | None:
        key = match_key(message)
        return next((e for e in self.entries if e.key == key), None)


def _entry(raw: object, number: int) -> Entry:
    if not isinstance(raw, dict):
        raise KnowledgeBaseError(f"entry {number}: expected 'emitter:', 'message:' ... lines")
    label = f"entry {number} ({raw.get('emitter', '?')})"
    unknown = sorted(map(str, set(raw) - set(_REQUIRED) - set(_OPTIONAL)))
    if unknown:
        raise KnowledgeBaseError(f"{label}: unknown field: {', '.join(unknown)}")
    missing = [f for f in _REQUIRED if f not in raw]
    if missing:
        raise KnowledgeBaseError(f"{label}: missing: {', '.join(missing)}")
    for field_name, value in raw.items():
        # YAML reads a bare `no`, `yes` or `1001` as a boolean or number.
        if not isinstance(value, str) or not value.strip():
            raise KnowledgeBaseError(
                f"{label}: {field_name} must be text (got {value!r}); put it in quotes"
            )
    if raw["scope"] not in SCOPES:
        raise KnowledgeBaseError(f"{label}: scope must be one of {SCOPES}, not {raw['scope']!r}")
    if raw["status"] not in STATUSES:
        raise KnowledgeBaseError(
            f"{label}: status must be one of {STATUSES}, not {raw['status']!r}"
        )
    if not re.fullmatch(EMITTER, raw["emitter"].strip()):
        raise KnowledgeBaseError(
            f"{label}: emitter {raw['emitter']!r} is not a name as Bernese prints one; "
            "give only the name after SR / PG / PGM / FN, e.g. GTOCNL"
        )
    kind = kind_of(raw["message"])
    if not kind:
        raise KnowledgeBaseError(
            f"{label}: message {raw['message']!r} has nothing left to match once "
            "numbers and quoted text are ignored"
        )
    return Entry(
        emitter=raw["emitter"].strip(),
        message=raw["message"].strip(),
        kind=kind,
        scope=raw["scope"],
        status=raw["status"],
        diagnosis=" ".join(raw["diagnosis"].split()),
        remedy=" ".join(raw["remedy"].split()),
        source=" ".join(raw["source"].split()),
        confirm=" ".join(raw["confirm"].split()) if "confirm" in raw else None,
        number=number,
    )


def loads(text: str) -> KnowledgeBase:
    try:
        data = yaml.load(text, Loader=_Loader)  # a SafeLoader subclass: still safe
    except yaml.YAMLError as exc:
        raise KnowledgeBaseError(
            f"not valid YAML: {exc}\n"
            "Most often a one-line value containing ': ' that needs single quotes."
        ) from exc
    if not isinstance(data, dict) or set(data) != {"entries"}:
        raise KnowledgeBaseError("the file must contain one top-level key, 'entries:'")
    if not isinstance(data["entries"], list):
        raise KnowledgeBaseError("'entries:' must be a list of '- emitter: ...' rows")

    entries: list[Entry] = []
    seen: dict[tuple[str, str], int] = {}
    for number, raw in enumerate(data["entries"], start=1):
        entry = _entry(raw, number)
        if entry.key in seen:
            raise KnowledgeBaseError(
                f"entry {number} ({entry.emitter}) matches the same error as entry "
                f"{seen[entry.key]}; merge the two"
            )
        seen[entry.key] = number
        entries.append(entry)
    return KnowledgeBase(tuple(entries))


def load(path: Path = DEFAULT_PATH) -> KnowledgeBase:
    try:
        return loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise KnowledgeBaseError(f"{path}: cannot read: {exc}") from exc
    except KnowledgeBaseError as exc:
        raise KnowledgeBaseError(f"{path}: {exc}") from exc


def _header(m: BernMessage) -> str:
    text = f"{'***' if m.severity == 'error' else '###'} {m.emitter_type} {m.emitter}"
    if m.program and m.emitter_type not in ("PG", "PGM"):
        text += f", PG {m.program}"
    return f"{text}: {m.headline}" if m.headline else text


def _para(label: str, text: str) -> str:
    return textwrap.fill(
        text, width=78, initial_indent=f"{label}: ", subsequent_indent=" " * (len(label) + 2)
    )


def explain(report: StepReport, kb: KnowledgeBase) -> str:
    """What a person needs to read about one step: the error, then the row."""
    if not report.failed:
        return "The step did not fail."
    lines = [f"{report.failed_program} failed."]
    cause = report.cause
    if cause is None:
        lines.append("There is no *** message before the failure. UNKNOWN: read the whole file.")
        return "\n".join(lines)

    lines.append(f"  {_header(cause)}")
    lines.extend(f"      {d}" for d in cause.detail)
    entry = kb.lookup(cause)
    if entry is None:
        lines.append(
            "UNKNOWN: no row in the knowledge base for "
            f"({cause.emitter}, {cause.kind}). Diagnose it, then add a row."
        )
        return "\n".join(lines)

    lines.append(
        f"Known error, entry {entry.number} (scope: {entry.scope}, status: {entry.status})"
    )
    lines.append(_para("Diagnosis", entry.diagnosis))
    lines.append(_para("Remedy", entry.remedy))
    if entry.confirm:
        lines.append(_para("Confirm", entry.confirm))
    lines.append(_para("Source", entry.source))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bernese_workflow.bpe_knowledge",
        description="Explain failed BPE steps from their .PRT or .LOG files.",
    )
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--kb", type=Path, default=DEFAULT_PATH, help="knowledge base YAML")
    args = parser.parse_args(argv)

    try:
        kb = load(args.kb)
    except KnowledgeBaseError as exc:
        print(f"knowledge base invalid: {exc}", file=sys.stderr)
        return 2

    status = 0
    for path in args.files:
        report = scan_file(path)
        print(f"== {path}")
        print(explain(report, kb))
        print()
        if report.failed and (report.cause is None or kb.lookup(report.cause) is None):
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
