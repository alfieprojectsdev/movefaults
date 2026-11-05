"""Tests for scripts/export_field_equipment.py.

The fake connection records every statement, which is how "every query runs
inside a READ ONLY transaction, rolled back and never committed" is checked
without a database. The last test uses a real Postgres when one is reachable
(the docker-compose database on 5433, as the field-ops integration tests use)
and skips otherwise; it reads, and its one attempted write is refused by the
read-only transaction it is testing.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "export_field_equipment", _SCRIPTS / "export_field_equipment.py"
)
exp = importlib.util.module_from_spec(_spec)
sys.modules["export_field_equipment"] = exp
_spec.loader.exec_module(exp)

NOW = dt.datetime(2026, 11, 5, 17, 41, tzinfo=dt.UTC)


class FakeCursor:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn
        self._rows: list[tuple] = []

    def execute(self, sql: str) -> None:
        self.conn.log.append(sql)
        if "FROM field_ops.logsheets" in sql:
            self._rows = self.conn.logsheets
        elif "FROM field_ops.equipment_history" in sql:
            self._rows = self.conn.history
        else:
            self._rows = []

    def fetchall(self) -> list[tuple]:
        return self._rows


class FakeConn:
    def __init__(self, logsheets: list[tuple], history: list[tuple]) -> None:
        self.logsheets, self.history = logsheets, history
        self.log: list[str] = []
        self.autocommit = True
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def rollback(self) -> None:
        self.log.append("ROLLBACK")

    def commit(self) -> None:  # pragma: no cover -- must never be called
        self.commits += 1


def _logsheet(**over) -> tuple:
    row = dict.fromkeys(exp.LOGSHEET_COLUMNS)
    row.update(
        id=7, client_uuid=uuid.UUID(int=1), station_code="ALCO",
        visit_date=dt.date(2026, 3, 10),
        arrival_time=dt.datetime(2026, 3, 10, 9, 30, tzinfo=dt.timezone(dt.timedelta(hours=8))),
        equipment_changed=True, receiver_model_before="Leica GR50", antenna_type_before="Leica AR20",
        receiver_model_after="Trimble NetR9",
    )  # fmt: skip
    row.update(over)
    return tuple(row[c] for c in exp.LOGSHEET_COLUMNS)


def _history(**over) -> tuple:
    row = dict.fromkeys(exp.HISTORY_COLUMNS)
    row.update(
        id=1,
        station_code="ALCO",
        model="Leica GR50",
        antenna_model="Leica AR20",
        radome_type="LEIM",
    )
    row.update(over)
    return tuple(row[c] for c in exp.HISTORY_COLUMNS)


def test_every_query_runs_inside_one_read_only_transaction_that_is_rolled_back() -> None:
    conn = FakeConn([_logsheet()], [_history()])
    exp.export(conn, NOW)
    assert conn.autocommit is False
    # A clean start, then SET TRANSACTION first, then the two SELECTs, then rollback.
    assert conn.log[0] == "ROLLBACK"
    assert conn.log[1] == exp.READ_ONLY
    assert "READ ONLY" in exp.READ_ONLY and exp.READ_ONLY.startswith("SET TRANSACTION")
    selects = conn.log[2:-1]
    assert len(selects) == 2 and all(s.startswith("SELECT ") for s in selects)
    assert conn.log[-1] == "ROLLBACK"
    assert conn.commits == 0


def test_no_query_writes() -> None:
    for sql, _ in exp.QUERIES.values():
        head = sql.split()[0].upper()
        assert head == "SELECT", sql
        words = set(re.findall(r"[A-Z_]+", sql.upper()))  # whole words: created_at is not CREATE
        assert not words & {"INSERT", "UPDATE", "DELETE", "TRUNCATE", "ALTER", "DROP", "CREATE"}, (
            sql
        )


def test_the_document_carries_exported_at_counts_and_plain_values() -> None:
    doc = exp.export(FakeConn([_logsheet(), _logsheet(id=8)], [_history()]), NOW)
    assert doc["format"] == "field-ops-equipment-export" and doc["version"] == 1
    assert doc["exported_at"] == "2026-11-05T17:41:00+00:00"
    assert doc["counts"] == {"logsheets": 2, "equipment_history": 1}
    sheet = doc["logsheets"][0]
    assert set(sheet) == set(exp.LOGSHEET_COLUMNS)
    assert sheet["visit_date"] == "2026-03-10"
    assert sheet["arrival_time"] == "2026-03-10T09:30:00+08:00"
    assert sheet["client_uuid"] == str(uuid.UUID(int=1))
    json.dumps(doc)  # every value is plain JSON


def test_every_before_and_after_equipment_column_is_exported() -> None:
    import field_ops.models as m

    cols = {c.name for c in m.LogSheet.__table__.columns}
    equipment = {c for c in cols if c.endswith(("_before", "_after", "_before_m", "_after_m"))}
    assert equipment, (
        "the model has no before/after columns: the test is looking in the wrong place"
    )
    assert equipment <= set(exp.LOGSHEET_COLUMNS)
    assert set(exp.HISTORY_COLUMNS) == {c.name for c in m.EquipmentHistory.__table__.columns}


def test_the_report_reads_what_the_export_writes(tmp_path: Path) -> None:
    from bernese_workflow.equipment_check import read_logsheet_export

    out = tmp_path / "x" / "field_equipment.json"
    exp.write_atomic(exp.export(FakeConn([_logsheet()], [_history()]), NOW), out)
    got = read_logsheet_export(out)
    assert got.exported_at == "2026-11-05T17:41:00+00:00"
    assert got.counts == {"logsheets": 1, "equipment_history": 1}
    assert [p.name for p in out.parent.iterdir()] == ["field_equipment.json"], "no temporary left"


def test_main_never_prints_the_database_url(monkeypatch, tmp_path, capsys) -> None:
    import psycopg2

    secret = "postgresql://someone:s3cret@db.example.invalid:5432/x"
    monkeypatch.setenv("DATABASE_URL", secret)

    def refuse(url):
        assert url == secret
        raise psycopg2.OperationalError("could not connect to server")

    monkeypatch.setattr(psycopg2, "connect", refuse)
    assert exp.main(["--out", str(tmp_path / "f.json")]) == 2
    out = capsys.readouterr()
    assert "s3cret" not in out.err + out.out and secret not in out.err + out.out
    assert not (tmp_path / "f.json").exists()


# --- against a real Postgres, when there is one ----------------------------------------

TEST_URL = os.environ.get(
    "FIELD_OPS_TEST_DATABASE_URL",
    "postgresql+asyncpg://pogf_user:pogf_password@localhost:5433/pogf_db",
).replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture
def pg():
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        conn = psycopg2.connect(TEST_URL, connect_timeout=3)
    except psycopg2.Error as exc:
        pytest.skip(f"no PostgreSQL for the export test: {type(exc).__name__}")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT to_regclass('field_ops.logsheets'), to_regclass('field_ops.equipment_history')"
        )
        if None in cur.fetchone():
            conn.close()
            pytest.skip("the field_ops tables are not migrated in this database")
    conn.rollback()
    yield conn
    conn.close()


def test_against_postgres_the_counts_match_and_a_write_is_refused(pg) -> None:
    import psycopg2.errors

    doc = exp.export(pg, NOW)
    with pg.cursor() as cur:
        cur.execute("SELECT count(*) FROM field_ops.logsheets")
        assert doc["counts"]["logsheets"] == cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM field_ops.equipment_history")
        assert doc["counts"]["equipment_history"] == cur.fetchone()[0]
    pg.rollback()
    # The transaction mode the export uses refuses a write before any constraint is checked.
    with pg.cursor() as cur:
        cur.execute(exp.READ_ONLY)
        with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
            cur.execute("DELETE FROM field_ops.equipment_history WHERE false")
    pg.rollback()
