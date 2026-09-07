import importlib

import pytest

from api.db import Database


@pytest.fixture
def client(tmp_path):
    app_module = importlib.import_module("dashboard.app")
    app_module._db = Database(str(tmp_path / "dash.db"))
    app_module._db.initialize()
    app_module._scanner_status.update(running=False, progress="Idle")
    app_module._stop_event = None
    app_module._scan_tokens = None

    yield app_module.app.test_client()

    app_module._db.close()


def test_index_renders_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.content_type


def test_stats_endpoint(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] >= 0


def test_keys_endpoint(client):
    r = client.get("/api/keys")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_scan_status_endpoint(client):
    r = client.get("/api/scan/status")
    assert r.status_code == 200
    assert r.get_json()["running"] is False


def test_scan_start_requires_tokens(client):
    r = client.post("/api/scan/start", json={})
    assert r.status_code == 400


def test_scan_start_rejects_short_tokens(client):
    r = client.post("/api/scan/start", json={"tokens": ["short"]})
    assert r.status_code == 400


def test_revalidate_empty_db(client):
    r = client.post("/api/keys/revalidate")
    assert r.status_code == 200
    assert r.get_json() == {"rechecked": 0}


def test_report_key_requires_fields(client):
    r = client.post("/api/keys/report", json={})
    assert r.status_code == 400


def test_report_key_rejects_path_traversal(client):
    r = client.post(
        "/api/keys/report",
        json={"owner": "..", "repo": "evil", "key": "k", "token": "t"},
    )
    assert r.status_code == 400
