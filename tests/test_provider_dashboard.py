import importlib

import pytest

from api.db import Database


@pytest.fixture
def client(tmp_path):
    app_module = importlib.import_module("api.dashboard.app")
    app_module._db = Database(str(tmp_path / "dash.db"))
    app_module._db.initialize()
    app_module._scanner_status.update(running=False, progress="Idle")
    app_module._stop_event = None
    app_module._scan_tokens = None

    yield app_module.app.test_client()

    app_module._db.close()


@pytest.fixture
def no_env_keys(monkeypatch):
    for v in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(v, raising=False)


def test_providers_endpoint(client):
    r = client.get("/api/providers")
    assert r.status_code == 200
    data = r.get_json()
    ids = {p["id"] for p in data}
    assert {"openai", "anthropic", "google", "openrouter"} <= ids
    # never expose raw keys
    for p in data:
        assert "key" not in p or p.get("key") is None


def test_services_endpoint(client):
    r = client.get("/api/services")
    assert r.status_code == 200
    services = {s["service"] for s in r.get_json()}
    assert "OpenAI" in services
    assert "Groq" in services


def test_models_endpoint(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    data = r.get_json()
    assert "gpt-4o" in {m["id"] for m in data}


def test_models_endpoint_filter(client):
    r = client.get("/api/models?provider=anthropic")
    data = r.get_json()
    assert data
    assert all(m["provider"] == "anthropic" for m in data)


def test_keys_status_endpoint(client, no_env_keys):
    r = client.get("/api/keys/status")
    assert r.status_code == 200
    blob = r.get_json()
    assert blob["openai"]["status"] == "not_configured"
    for pid, info in blob.items():
        assert "key" not in info or info.get("key") is None


def test_keys_status_masks_value(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abcdef0123456789abcdef0123456789")
    r = client.get("/api/keys/status")
    blob = r.get_json()
    assert "sk-abcdef0123456789abcdef0123456789" not in str(blob)
    assert "••" in str(blob)


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "openai" in r.get_json()


def test_validate_endpoint_missing(client, no_env_keys):
    r = client.post("/api/validate/openai", json={})
    assert r.status_code == 200
    res = r.get_json()
    assert res["valid"] is False


def test_validate_endpoint_unknown_provider(client):
    r = client.post("/api/validate/made-up", json={})
    assert r.status_code == 200
    assert r.get_json()["valid"] is False


def test_models_discover_endpoint_requires_provider(client):
    r = client.post("/api/models/discover", json={})
    assert r.status_code == 400


def test_models_discover_no_key(client, no_env_keys):
    r = client.post("/api/models/discover", json={"provider": "openai"})
    assert r.status_code == 400
    assert "API key" in r.get_json()["error"]