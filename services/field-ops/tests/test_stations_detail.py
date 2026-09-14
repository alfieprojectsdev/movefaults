"""
`GET /api/v1/stations` returns the station detail the app needs to say
something about a place, not just its code.

WHY THESE TESTS EXIST IN THIS SHAPE
-----------------------------------
The endpoint reads `public.stations` through raw SQL, because the ORM model
for that table lives in the repo-root `src/db/models.py` and field-ops
deliberately does not import across the service boundary. Raw SQL means a
mistyped column name is invisible until it reaches a real PostgreSQL: the
SQLite fixture cannot create `public.stations` at all, and `conftest`'s
`pg_engine` skips when Docker is down.

So a typo in the eight columns added on 2026-09-15 would ship green.

`test_every_selected_column_exists` closes that without a database. It reads
the SELECT list out of the router and checks each name against the ORM model's
own columns — the same table, from the one place in this repo that declares its
shape. It is a static check of a dynamic query, and it fails loudly on a typo
that no other test in this suite can see.
"""

import re
from datetime import date
from pathlib import Path

import pytest

from field_ops.routers.stations import StationOut

ROUTER = Path(__file__).resolve().parents[1] / "src" / "field_ops" / "routers" / "stations.py"


def _selected_columns() -> list[str]:
    """The bare column names in the `FROM stations` SELECT list."""
    src = ROUTER.read_text(encoding="utf-8")
    m = re.search(r"SELECT\s+(.*?)\s+FROM stations", src, re.S)
    assert m, "could not find the stations SELECT -- has the query been restructured?"
    cols = []
    for raw in m.group(1).split(","):
        line = raw.strip()
        if not line:
            continue
        # `ST_Y(location::geometry) AS latitude` names a column inside the
        # call, not at the top level. Take what the function reads.
        inner = re.search(r"ST_[XY]\((\w+)", line)
        cols.append(inner.group(1) if inner else line.split()[0])
    return cols


def test_every_selected_column_is_declared_on_the_station_model():
    """Introspects the ORM MODEL, not a database.

    Naming matters here. `src/db/models.py` is this repo's declaration of what
    `public.stations` looks like; it is not evidence that any particular
    database matches it. This test catches a column name that exists nowhere
    in the project, which is the mistake this change could plausibly make.

    It does NOT prove production has the columns. What does:

      * `001_create_stations.py` CREATE TABLE -- agency, date_installed
      * `004_expand_stations.py` ALTER TABLE  -- monitoring_method,
        municipality, province, region, land_owner, maintenance_interval_days

    Both use `op.execute` with raw SQL rather than `op.add_column`, so a grep
    for the alembic idiom finds neither and concludes the columns are
    unmanaged. A reviewer did exactly that on this PR.
    """
    from src.db.models import Station

    actual = {c.name for c in Station.__table__.columns}
    missing = [c for c in _selected_columns() if c not in actual]
    assert not missing, (
        f"SELECT names columns absent from public.stations: {missing}. "
        f"Raw SQL, so this fails at runtime against Postgres and nowhere else."
    )


def test_the_detail_fields_are_actually_selected():
    """The widening is in the query, not only in the response model.

    A field present on StationOut but missing from the SELECT is silently
    None for every inventory row -- which looks like absent data rather than
    a bug, and is the failure this pair of tests exists to separate.
    """
    selected = set(_selected_columns())
    for field in (
        "municipality", "province", "region", "monitoring_method",
        "land_owner", "date_installed", "agency", "maintenance_interval_days",
    ):
        assert field in selected, f"{field} is on StationOut but not in the SELECT"


def test_detail_fields_default_to_none():
    """Every added field is optional on both sources.

    A proposal carries only what the observer typed at the monument, and the
    inventory is itself incomplete for older sites. A required field here
    would reject rows that are legitimately partial.
    """
    s = StationOut(
        station_code="TSTA", name=None, latitude=None, longitude=None,
        elevation=None, fault_segment=None, status=None,
    )
    assert s.municipality is None
    assert s.monitoring_method is None
    assert s.land_owner is None
    assert s.date_installed is None
    assert s.maintenance_interval_days is None
    assert s.source == "inventory"


def test_detail_fields_round_trip():
    s = StationOut(
        station_code="PPPC", name="Puerto Princesa City", latitude=9.74, longitude=118.74,
        elevation=12.0, fault_segment=None, status="active",
        municipality="Puerto Princesa", province="Palawan", region="MIMAROPA",
        monitoring_method="continuous", land_owner="LGU",
        date_installed=date(2015, 3, 1), agency="PHIVOLCS",
        maintenance_interval_days=180,
    )
    assert s.municipality == "Puerto Princesa"
    assert s.date_installed == date(2015, 3, 1)
    assert s.maintenance_interval_days == 180


def test_last_visit_is_not_a_station_field():
    """`last_visit` is in the seed CSV and NOT in the table.

    The design mock shows "last sheet 14 Mar" on the station screen, which is
    a logsheets question. Exposing a `last_visit` column here would be a
    second, quietly stale answer to it -- the CSV value is whatever was true
    when somebody last edited the file.
    """
    assert not hasattr(StationOut, "last_visit")
    assert "last_visit" not in _selected_columns()


# ---------------------------------------------------------------------------
# The real thing, when a PostgreSQL is available
# ---------------------------------------------------------------------------
#
# The static check above proves the column NAMES exist. It cannot prove the
# query runs: a type the driver cannot adapt, a PostGIS call that changed
# signature, an ambiguous name once a join appears. Only execution shows that,
# and an unexecuted query is inert rather than proven.
#
# Skips when Docker is down, per conftest's pg_engine. A fixture that reddens
# the suite on a laptop with nothing running gets deleted, and then covers
# nothing at all.


@pytest.mark.asyncio
async def test_the_widened_query_actually_executes(pg_session):
    """Run the router's own SELECT against a real PostGIS table.

    Reads the SQL out of the router rather than restating it, so the test
    cannot drift into passing while the endpoint is broken -- which is the
    usual fate of a test that copies the query it is meant to guard.
    """
    import re

    from sqlalchemy import text as sa_text

    src = ROUTER.read_text(encoding="utf-8")
    m = re.search(r'text\("""\s*(SELECT.*?FROM stations.*?)"""\)', src, re.S)
    assert m, "could not extract the stations query"

    result = await pg_session.execute(sa_text(m.group(1)))
    rows = result.mappings().all()

    # An empty stations table is a legitimate state for a fresh database, so
    # this asserts the SHAPE rather than the content.
    expected = {
        "station_code", "name", "latitude", "longitude", "elevation",
        "fault_segment", "status", "municipality", "province", "region",
        "monitoring_method", "land_owner", "date_installed", "agency",
        "maintenance_interval_days",
    }
    if rows:
        assert expected <= set(rows[0].keys())
        # Every row must satisfy the response model. A column the driver
        # returns in a form Pydantic rejects fails here and nowhere else.
        for row in rows[:25]:
            StationOut(**dict(row), source="inventory")
    else:
        assert expected <= set(result.keys())
