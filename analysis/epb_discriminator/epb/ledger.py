"""Hypothesis ledger with a verifier: no status change without stored evidence.

Each claim is a hypothesis (H_eq, H_epb, H_glitch) with a status and a
confidence. Evidence entries record a check's result and the SHA-256 of the
check's raw output. update() is refused unless it cites the hash of evidence
already stored for that same claim, so a status can only move on something a
check actually produced. That is the whole rule for now.
"""

from __future__ import annotations

import hashlib
import itertools

RESULTS = {"support", "reject", "insufficient", "reject_H_eq"}
STATUSES = {"open", "supported", "rejected"}


class LedgerError(ValueError):
    pass


class Ledger:
    def __init__(self) -> None:
        self.claims: dict[str, dict] = {}
        self._ids = itertools.count(1)

    def open_claim(
        self, hypothesis: str, confidence: float = 0.5, parent: str | None = None
    ) -> str:
        cid = f"c{next(self._ids)}"
        self.claims[cid] = {
            "id": cid,
            "hypothesis": hypothesis,
            "status": "open",
            "confidence": confidence,
            "evidence": [],
            "parent": parent,
        }
        return cid

    def add_evidence(
        self, cid: str, *, check: str, result: str, value: float, output: bytes
    ) -> dict:
        if result not in RESULTS:
            raise LedgerError(f"result must be one of {sorted(RESULTS)}, not {result!r}")
        ev = {
            "check": check,
            "result": result,
            "value": value,
            "output_hash": hashlib.sha256(output).hexdigest(),
        }
        self.claims[cid]["evidence"].append(ev)
        return ev

    def update(
        self,
        cid: str,
        *,
        status: str | None = None,
        confidence: float | None = None,
        cite: str | None,
    ):
        claim = self.claims[cid]
        if not cite or cite not in {e["output_hash"] for e in claim["evidence"]}:
            raise LedgerError(
                "a status or confidence change must cite evidence stored for this claim"
            )
        if status is not None:
            if status not in STATUSES:
                raise LedgerError(f"status must be one of {sorted(STATUSES)}")
            claim["status"] = status
        if confidence is not None:
            claim["confidence"] = confidence
