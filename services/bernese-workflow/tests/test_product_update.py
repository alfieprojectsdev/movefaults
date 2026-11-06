"""Tests for bernese-update-products. No network: the mirror is a dictionary.

Each behaviour here is one a nightly job could get silently wrong: replacing a file,
keeping a broken one, calling a normal delay a failure, or updating a table that changes
results for days already solved.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import gzip
import http.client
import json
from pathlib import Path

import pytest
from bernese_workflow import product_update as pu
from bernese_workflow.product_update import NotPublished, Result

TODAY = dt.date(2026, 11, 6)
DAY = dt.date(2026, 10, 20)  # DOY 293
GOOD = gzip.compress(b"a product\n")


def names(day: dt.date) -> list[tuple[str, str]]:
    year, doy = pu.day_name(day)
    return [(folder, pattern.format(y=year, d=doy)) for _, folder, pattern in pu.PRODUCTS]


def mirror(*days: dt.date):
    urls = {
        f"{pu.MIRROR}/CODE/{d.year}/{name}": GOOD for d in days for _, name in names(d)
    }

    def get(url: str) -> bytes:
        if url not in urls:
            raise NotPublished(url)
        return urls[url]

    get.urls = urls  # type: ignore[attr-defined]
    return get


def test_a_published_day_is_fetched_into_the_folders_the_plan_page_checks(tmp_path: Path) -> None:
    result = Result()
    assert pu.fetch_day(DAY, tmp_path, today=TODAY, result=result, get=mirror(DAY))
    for folder, name in names(DAY):
        assert (tmp_path / folder / name).read_bytes() == GOOD
    assert len(result.fetched) == 5
    assert not list(tmp_path.rglob("*.part"))


def test_an_existing_file_is_never_replaced_or_fetched(tmp_path: Path) -> None:
    folder, name = names(DAY)[0]
    existing = tmp_path / folder / name
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"what a run already used")
    asked: list[str] = []
    get = mirror(DAY)

    def counting(url: str) -> bytes:
        asked.append(url)
        return get(url)

    pu.fetch_day(DAY, tmp_path, today=TODAY, result=Result(), get=counting)
    assert existing.read_bytes() == b"what a run already used"
    assert not [u for u in asked if name in u]


@pytest.mark.parametrize("body", [GOOD[:8], b"<html>not gzip</html>", b"", gzip.compress(b"")])
def test_a_broken_download_is_an_error_and_never_kept(tmp_path: Path, body: bytes) -> None:
    get = mirror(DAY)
    for url in get.urls:  # type: ignore[attr-defined]
        get.urls[url] = body  # type: ignore[attr-defined]
    result = Result()
    assert not pu.fetch_day(DAY, tmp_path, today=TODAY, result=result, get=get)
    assert len(result.errors) == 5
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


def test_a_recent_day_not_published_is_waiting_not_a_problem(tmp_path: Path) -> None:
    result = Result()
    recent = TODAY - dt.timedelta(days=5)
    assert not pu.fetch_day(recent, tmp_path, today=TODAY, result=result, get=mirror())
    assert result.waiting == 5
    assert result.errors == [] and result.late == []


def test_an_old_day_not_published_is_late(tmp_path: Path) -> None:
    result = Result()
    old = TODAY - dt.timedelta(days=30)
    pu.fetch_day(old, tmp_path, today=TODAY, result=result, get=mirror())
    assert len(result.late) == 5
    assert result.waiting == 0
    assert "orbits" in result.late[0]


def test_a_network_failure_on_one_file_doesnt_stop_the_rest(tmp_path: Path) -> None:
    get = mirror(DAY)
    bad = next(u for u in get.urls if "ORB" in u)  # type: ignore[attr-defined]

    def flaky(url: str) -> bytes:
        if url == bad:
            raise OSError("connection reset")
        return get(url)

    result = Result()
    assert not pu.fetch_day(DAY, tmp_path, today=TODAY, result=result, get=flaky)
    assert len(result.errors) == 1 and "connection reset" in result.errors[0]
    assert len(result.fetched) == 4


def test_a_connection_cut_mid_body_is_an_error_not_a_crash(tmp_path: Path) -> None:
    def cut(url: str) -> bytes:
        raise http.client.IncompleteRead(b"partial")  # not an OSError

    result = Result()
    assert not pu.fetch_day(DAY, tmp_path, today=TODAY, result=result, get=cut)
    assert len(result.errors) == 5


def test_a_failed_write_is_an_error_and_leaves_nothing(tmp_path: Path) -> None:
    (tmp_path / "COD0OPSFIN").write_text("a file where the folder should be")
    result = Result()
    assert not pu.fetch_day(DAY, tmp_path, today=TODAY, result=result, get=mirror(DAY))
    assert len(result.errors) == 4
    assert len(result.fetched) == 1  # the ionosphere map, in another folder
    assert not list(tmp_path.rglob("*.part"))


def test_an_empty_existing_file_is_reported_and_left_alone(tmp_path: Path) -> None:
    folder, name = names(DAY)[0]
    empty = tmp_path / folder / name
    empty.parent.mkdir(parents=True)
    empty.write_bytes(b"")
    result = Result()
    assert not pu.fetch_day(DAY, tmp_path, today=TODAY, result=result, get=mirror(DAY))
    assert empty.read_bytes() == b""
    assert len(result.errors) == 1 and name in result.errors[0]


def test_dry_run_writes_nothing_and_asks_the_mirror_nothing(tmp_path: Path) -> None:
    def refuse(url: str) -> bytes:
        raise AssertionError("no request in a dry run")

    assert not pu.fetch_day(DAY, tmp_path, today=TODAY, result=Result(), get=refuse, dry_run=True)
    assert not list(tmp_path.rglob("*"))


def test_range_reports_the_latest_complete_day(tmp_path: Path) -> None:
    next_day = DAY + dt.timedelta(days=1)
    result = Result()
    pu.fetch_range(DAY, next_day + dt.timedelta(days=1), tmp_path, result, get=mirror(DAY, next_day))
    assert result.latest_complete == "2026 DOY 294"


def test_the_year_boundary_uses_the_days_own_year(tmp_path: Path) -> None:
    newyear = dt.date(2027, 1, 1)
    get = mirror(newyear)
    assert any("/CODE/2027/COD0OPSFIN_20270010000" in u for u in get.urls)  # type: ignore[attr-defined]
    assert pu.fetch_day(newyear, tmp_path, today=dt.date(2027, 1, 20), result=Result(), get=get)


# --- files that are compared, never replaced --------------------------------------


def _watched(tmp_path: Path, sizes: dict[str, int]):
    config, ref = tmp_path / "config", tmp_path / "ref"
    config.mkdir()
    ref.mkdir()
    (config / "SATELLIT_I20.SAT").write_bytes(b"x" * 100)
    (config / "DATUM.BSW").write_bytes(b"y" * 50)

    def head(url: str) -> tuple[int, float | None]:
        name = url.rsplit("/", 1)[1]
        if name not in sizes:
            raise NotPublished(url)
        return sizes[name], 1_793_000_000.0

    return config, ref, head


def _entry(out: list[dict], name: str) -> dict:
    return next(e for e in out if e["file"] == name)


def test_a_file_the_mirror_lacks_is_listed_not_dropped(tmp_path: Path) -> None:
    config, ref, head = _watched(tmp_path, {})
    out, errors = pu.compare_watched(config, ref, 2026, head=head)
    assert errors == []
    assert len(out) == len(pu.WATCHED)
    assert all(e["not_on_mirror"] and not e["out_of_date"] for e in out)


def test_a_head_without_a_length_is_an_error_not_a_difference(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        headers: dict[str, str] = {}

        def __enter__(self):
            return self

        def __exit__(self, *exc: object) -> None:
            pass

    monkeypatch.setattr(pu, "_url_open", lambda url, method="GET": Response())
    with pytest.raises(ValueError):
        pu.http_head("https://mirror/DATUM.BSW")


def test_a_different_size_is_out_of_date_and_nothing_is_written(tmp_path: Path) -> None:
    config, ref, head = _watched(tmp_path, {"SATELLIT_I20.SAT": 200})
    before = (config / "SATELLIT_I20.SAT").read_bytes()
    out, errors = pu.compare_watched(config, ref, 2026, head=head)
    assert errors == []
    assert _entry(out, "SATELLIT_I20.SAT")["out_of_date"] is True
    assert (config / "SATELLIT_I20.SAT").read_bytes() == before
    assert sorted(p.name for p in config.iterdir()) == ["DATUM.BSW", "SATELLIT_I20.SAT"]


def test_a_newer_date_with_the_same_size_is_not_out_of_date(tmp_path: Path) -> None:
    # The mirror re-uploads whole folders, so its date alone says nothing.
    config, ref, head = _watched(tmp_path, {"DATUM.BSW": 50})
    out, _ = pu.compare_watched(config, ref, 2026, head=head)
    assert _entry(out, "DATUM.BSW")["out_of_date"] is False


def test_a_watched_file_missing_here_is_out_of_date(tmp_path: Path) -> None:
    config, ref, head = _watched(tmp_path, {"IGS20.FIX": 10})
    out, _ = pu.compare_watched(config, ref, 2026, head=head)
    assert _entry(out, "IGS20.FIX")["out_of_date"] is True


def test_the_satellite_problem_file_follows_the_year(tmp_path: Path) -> None:
    config, ref, head = _watched(tmp_path, {"SAT_2027.CRX": 10})
    out, _ = pu.compare_watched(config, ref, 2027, head=head)
    assert "aiub_size" in _entry(out, "SAT_2027.CRX")


def test_a_failed_comparison_is_reported(tmp_path: Path) -> None:
    config, ref, _ = _watched(tmp_path, {})

    def head(url: str) -> tuple[int, float | None]:
        raise OSError("no route")

    out, errors = pu.compare_watched(config, ref, 2026, head=head)
    assert out == []
    assert len(errors) == len(pu.WATCHED)


# --- the command ------------------------------------------------------------------


def test_main_writes_a_status_and_exits_1_on_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    datapool = tmp_path / "D"
    datapool.mkdir()
    monkeypatch.setenv("D", str(datapool))
    monkeypatch.setenv("CONFIG", str(tmp_path))

    def broken(url: str) -> bytes:
        raise OSError("mirror down")

    monkeypatch.setattr(pu, "http_get", broken)
    monkeypatch.setattr(pu, "http_head", lambda url: (_ for _ in ()).throw(NotPublished(url)))
    state = tmp_path / "state"
    assert pu.main(["--lookback", "0", "--state", str(state)]) == 1
    status = json.loads((state / "products/status.json").read_text())
    assert len(status["errors"]) == 5
    assert status["last_pass"]


def test_main_waits_for_no_one_and_fetches_nothing_if_a_pass_is_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    datapool = tmp_path / "D"
    datapool.mkdir()
    monkeypatch.setenv("D", str(datapool))

    def refuse(url: str) -> bytes:
        raise AssertionError("no request while another pass runs")

    monkeypatch.setattr(pu, "http_get", refuse)
    state = tmp_path / "state"
    (state / "products").mkdir(parents=True)
    with open(state / "products/lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert pu.main(["--lookback", "0", "--state", str(state)]) == 0
    assert not (state / "products/status.json").exists()


def test_main_refuses_a_missing_datapool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("D", str(tmp_path / "nope"))
    assert pu.main(["--state", str(tmp_path)]) == 2
