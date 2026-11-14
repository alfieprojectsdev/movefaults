"""HTTP routes: the browser's path from site list to export."""

import pytest
import velocity_reviewer.app as app_module
from fastapi.testclient import TestClient

ROWS = [
    "2020.0014  0.010000  0.020000  0.030000",
    "2020.0041  0.011000  0.021000  0.031000",
    "2020.0068  0.012000  0.022000  0.032000",
    "2020.0096  0.013000  0.023000  0.033000",
    "2020.0123  0.014000  0.024000  0.034000",
]


@pytest.fixture
def plots(tmp_path, monkeypatch):
    (tmp_path / "123").write_text("AAAA\nBBBB\n")
    (tmp_path / "AAAA").write_text("\n".join(ROWS) + "\n")
    (tmp_path / "offsets").write_text("AAAA 2020.0050 EQ\n")
    monkeypatch.setenv("VELOCITY_REVIEWER_PLOTS_DIR", str(tmp_path))
    # Module-level session state: reset it so tests don't leak into each other.
    monkeypatch.setattr(app_module, "_plots_dir", None)
    monkeypatch.setattr(app_module, "_sites", [])
    monkeypatch.setattr(app_module, "_selections", {})
    monkeypatch.setattr(app_module, "_done", set())
    return tmp_path


@pytest.fixture
def client(plots):
    return TestClient(app_module.app)


def test_index_serves_the_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()


def test_sites_lists_the_123_file(client):
    assert client.get("/api/sites").json() == {
        "sites": ["AAAA", "BBBB"],
        "done": [],
        "total": 2,
    }


def test_site_data_has_series_fit_and_offsets(client):
    data = client.get("/api/sites/aaaa/data").json()
    assert len(data["t"]) == len(ROWS)
    assert data["offsets"] == [{"year": 2020.005, "type": "EQ"}]
    assert data["current_selection"] == []
    assert {"ve", "vn", "vu", "iqr_outliers", "e_fit"} <= data.keys()


def test_site_not_in_123_is_404(client):
    assert client.get("/api/sites/ZZZZ/data").status_code == 404


def test_listed_site_without_plot_file_is_404(client):
    r = client.get("/api/sites/BBBB/data")
    assert r.status_code == 404
    assert "PLOT file" in r.json()["detail"]


def test_selection_round_trip(client):
    client.post("/api/sites/AAAA/outliers", json={"timestamps": [2020.0041]})
    assert client.get("/api/sites/AAAA/outliers").json() == {"timestamps": [2020.0041]}
    assert client.get("/api/sites/AAAA/data").json()["current_selection"] == [2020.0041]


def test_selection_for_unlisted_site_is_rejected(client, plots):
    """A typo'd site must not reach OUTLIERS.txt."""
    for route in ("outliers", "accept"):
        r = client.post(f"/api/sites/ZZZZ/{route}", json={"timestamps": [2020.0]})
        assert r.status_code == 404
    client.post("/api/export")
    assert "ZZZZ" not in (plots / "OUTLIERS.txt").read_text()


def test_accept_marks_done(client):
    r = client.post("/api/sites/AAAA/accept", json={"timestamps": []})
    assert r.json() == {"ok": True, "done_count": 1, "total": 2}
    assert client.get("/api/sites").json()["done"] == ["AAAA"]


def test_export_writes_outliers_and_strips_plot(client, plots):
    client.post("/api/sites/AAAA/accept", json={"timestamps": [2020.0041, 2020.0096]})
    r = client.post("/api/export").json()
    assert r["total_outliers"] == 2
    assert r["rows_removed"] == 2
    assert (plots / "OUTLIERS.txt").read_text() == "AAAA 2020.0041\nAAAA 2020.0096\n"
    kept = (plots / "AAAA").read_text().splitlines()
    assert kept == [ROWS[0], ROWS[2], ROWS[4]]
    assert (plots / "AAAA.bak").read_text().splitlines() == ROWS


def test_missing_env_var_is_an_error(monkeypatch):
    monkeypatch.delenv("VELOCITY_REVIEWER_PLOTS_DIR", raising=False)
    monkeypatch.setattr(app_module, "_plots_dir", None)
    with pytest.raises(RuntimeError, match="VELOCITY_REVIEWER_PLOTS_DIR"):
        TestClient(app_module.app).get("/api/sites")
