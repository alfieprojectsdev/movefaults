"""The production `offsets` catalog must stay clean — enforced, not assumed.

`offsets_catalog.validate_offsets_catalog` has existed and passed its unit
tests for some time. Nothing ever ran it against the real file. This does.

Why that matters more than an ordinary lint: the catalog is hand-maintained,
`parse_offsets_file` reads it verbatim, and `estimate_velocity` splits segments
on its epochs. A bad entry does not raise — it silently changes a published
velocity. That has already happened once, when BR14 and LUZD each carried
`2022.8159` before `2022.5695` and the out-of-order pair corrupted two sites'
fits (`velocity_outlier_policy_delta.md`).

These are unit tests rather than a CI-only check on purpose. GitHub Actions is
disabled at the repository level, so a workflow step alone would guard nothing;
`uv run pytest` is what actually runs today.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pogf_geodetic_suite.timeseries.offsets_catalog import (
    load_offsets_catalog,
    validate_offsets_catalog,
)

CATALOG = (
    Path(__file__).resolve().parents[3]
    / "docs" / "bern52" / "phivolcs-scripts" / "event-catalog" / "offsets"
)


@pytest.fixture(scope="module")
def catalog_path() -> Path:
    if not CATALOG.exists():
        pytest.skip(f"production catalog not present at {CATALOG}")
    return CATALOG


def test_production_catalog_has_no_findings(catalog_path):
    """The guard. Any malformed, duplicate or out-of-order entry fails here."""
    findings = validate_offsets_catalog(catalog_path)
    assert not findings, "offsets catalog has findings:\n" + "\n".join(
        f"  {f}" for f in findings
    )


def test_production_catalog_loads(catalog_path):
    """`load_offsets_catalog` raises on a bad line; this proves it does not."""
    by_station = load_offsets_catalog(catalog_path)
    assert by_station, "catalog parsed to nothing"


def test_every_station_is_in_chronological_order(catalog_path):
    """Stated separately from the validator because this is the failure that
    actually corrupted velocities, and it should fail by name."""
    for station, events in load_offsets_catalog(catalog_path).items():
        epochs = [e.date for e in events]
        assert epochs == sorted(epochs), f"{station} is out of chronological order: {epochs}"


def test_br14_and_luzd_stay_fixed(catalog_path):
    """Regression for the known corruption.

    Both carried 2022.8159 before 2022.5695. Named explicitly so a
    reintroduction fails with the site codes rather than a generic message.
    """
    by_station = load_offsets_catalog(catalog_path)
    for station in ("BR14", "LUZD"):
        if station not in by_station:
            continue
        epochs = [e.date for e in by_station[station]]
        assert epochs == sorted(epochs), f"{station} regressed: {epochs}"


def test_catalog_shape_is_what_settled_records(catalog_path):
    """SETTLED.md records 70 stations and 89 events, verified 2026-08-25.

    Not a correctness check -- the catalog is expected to grow. It fails when
    the count changes so that SETTLED gets updated in the same change, rather
    than drifting the way the maturity table did.
    """
    by_station = load_offsets_catalog(catalog_path)
    stations = len(by_station)
    events = sum(len(v) for v in by_station.values())
    assert (stations, events) == (70, 89), (
        f"catalog is now {stations} stations / {events} events, not 70/89. "
        "If that is intended, update this test and the SETTLED.md entry together."
    )
