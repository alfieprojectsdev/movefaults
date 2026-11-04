"""Synthetic Bernese station files shared by the station-file and run tests.

A plain module, not a conftest: these are functions to call, not fixtures.
"""

from __future__ import annotations

_STA_HEADER = [
    "SYNTHETIC STATION INFORMATION                                   01-JAN-26 00:00",
    "--------------------------------------------------------------------------------",
    "",
    "FORMAT VERSION: 1.03",
    "TECHNIQUE:      GNSS",
    "",
    "TYPE 002: STATION INFORMATION",
    "-----------------------------",
    "",
    "STATION NAME          FLG          FROM                   TO         "
    "RECEIVER TYPE         RECEIVER SERIAL NBR   REC #   "
    "ANTENNA TYPE          ANTENNA SERIAL NBR    ANT #    NORTH      EAST      UP",
    "****************      ***  YYYY MM DD HH MM SS  YYYY MM DD HH MM SS  "
    "********************  ********************  ******  "
    "********************  ********************  ******  ***.****  ***.****  ***.****",
]
_STA_FOOTER = [
    "",
    "",
    "TYPE 003: HANDLING OF STATION PROBLEMS",
    "-----------------------------",
    "",
]


def sta_row(name: str, start: str, end: str, receiver: str = "LEICA GR50") -> str:
    """One TYPE 002 row in Bernese's fixed columns: name 1-16, FROM 28-46,
    TO 49-67, receiver 70-89, antenna 122-141. ``end`` "" is a blank (open) TO."""
    assert len(name) <= 16 and len(start) == 19 and len(end) in (0, 19)
    row = (
        f"{name:<16}      001  {start}  {end or ' ' * 19}  "
        f"{receiver:<20}  {'':20}  999999  "
        f"{'LEIAR20         NONE':<20}  {'':20}  999999    0.0000    0.0000    0.0000"
    )
    assert row[27:46] == start and row[69:89].strip() == receiver
    return row


def sta_text(rows: list[tuple], newline: str = "\n") -> str:
    """A .STA file holding ``rows``, each (name, from, to[, receiver])."""
    lines = _STA_HEADER + [sta_row(*r) for r in rows] + _STA_FOOTER
    return newline.join(lines) + newline
