"""
fo008's downgrade: it must refuse, and it must say why.

The refusal is correct and is not what these tests are about. Restoring
fo007's wider unique index fails when a station code has more than one pending
claim -- exactly the rows fo008 exists to allow -- and deleting somebody's
field-collected site to make an index fit would destroy the record #228 was
written to preserve. gps3 verified that refusal against real Postgres with two
real claims, and nothing was deleted.

What was wrong is what the operator saw:

    sqlalchemy.exc.IntegrityError: could not create unique index
      "uq_station_proposals_pending_code"
    DETAIL:  Key (station_code)=(ZZDG) is duplicated.

An asyncpg traceback that happens to name the code, from which the reader has
to infer that the failure was deliberate rather than a broken migration.

WHY NOT A PRE-CHECK
-------------------
Counting pending claims before the rebuild was considered and refused in
review of #234. It is a second statement making a claim the index then
re-decides -- the same two-statement shape removed from `promote_proposal` in
c9f71d3 -- and rows can appear between the count and the rebuild. The guard
stays exactly where it is, in the index; only the explanation changes.

These tests stand in for the database by making `op.create_index` raise what
Postgres raises. That is honest about its limit: it proves the message, not
that Postgres raises IntegrityError here, which is what gps3's run proved.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from sqlalchemy.exc import IntegrityError

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "008_colliding_proposals.py"
)

# What Postgres actually said on gps3, 2026-09-21. Kept verbatim so the test
# exercises the real shape of the error, DETAIL line and all.
_PG_DETAIL = (
    'could not create unique index "uq_station_proposals_pending_code"\n'
    "DETAIL:  Key (station_code)=(ZZDG) is duplicated."
)


def _load():
    spec = importlib.util.spec_from_file_location("fo008", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Recorder:
    """Stands in for alembic's `op`. Records calls; can fail one of them."""

    def __init__(self, fail_create: bool):
        self.fail_create = fail_create
        self.calls: list[str] = []

    def drop_index(self, *a, **k):
        self.calls.append("drop_index")

    def drop_column(self, *a, **k):
        self.calls.append("drop_column")

    def create_index(self, *a, **k):
        self.calls.append("create_index")
        if self.fail_create:
            raise IntegrityError("CREATE UNIQUE INDEX ...", {}, Exception(_PG_DETAIL))


@pytest.fixture
def fo008(monkeypatch):
    module = _load()

    def install(fail_create: bool) -> _Recorder:
        rec = _Recorder(fail_create)
        monkeypatch.setattr(module, "op", rec)
        return rec

    return module, install


def test_a_refused_downgrade_says_it_was_refused_on_purpose(fo008):
    module, install = fo008
    install(fail_create=True)

    with pytest.raises(RuntimeError) as err:
        module.downgrade()

    msg = str(err.value)
    # That the refusal is deliberate, and what protects.
    assert "field-collected" in msg
    assert "nothing was deleted" in msg.lower()
    # What to do about it, in the terms the reconcile screen uses.
    assert "promote or reject" in msg.lower()
    assert "reconcile" in msg.lower()


def test_the_offending_code_is_still_named(fo008):
    """Postgres' DETAIL is the one line that says WHICH code. An explanation
    that dropped it would be friendlier and less useful than the traceback."""
    module, install = fo008
    install(fail_create=True)

    with pytest.raises(RuntimeError) as err:
        module.downgrade()

    assert "ZZDG" in str(err.value)


def test_the_original_error_is_chained_not_swallowed(fo008):
    """Anyone debugging deeper still needs the driver's exception."""
    module, install = fo008
    install(fail_create=True)

    with pytest.raises(RuntimeError) as err:
        module.downgrade()

    assert isinstance(err.value.__cause__, IntegrityError)


def test_the_column_is_not_dropped_when_the_index_refuses(fo008):
    """`collides_with` is the only record of which claims were contested, so
    nothing removes it until the step that can refuse has succeeded.

    Defensive rather than load-bearing under alembic: env.py wraps migrations
    in a transaction and Postgres DDL is transactional, so a refused rebuild
    would roll an earlier drop_column back anyway. This pins the order for the
    case where the statements run outside that transaction -- by hand, or
    from `--sql` output applied piecemeal."""
    module, install = fo008
    rec = install(fail_create=True)

    with pytest.raises(RuntimeError):
        module.downgrade()

    assert "drop_column" not in rec.calls


def test_a_downgrade_with_nothing_contested_still_goes_through(fo008):
    """The anchor. Every test above would pass if downgrade() always raised."""
    module, install = fo008
    rec = install(fail_create=False)

    module.downgrade()

    assert rec.calls == ["drop_index", "create_index", "drop_column"]
