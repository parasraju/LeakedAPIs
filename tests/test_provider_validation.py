import pytest
import requests

import api.providers.validation as validation
from api.providers.registry import get_provider


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json


@pytest.fixture
def fake_requests(monkeypatch):
    calls = []

    def install(models_response):
        def fake_get(url, headers=None, params=None, timeout=None):
            calls.append((url, headers or {}, params, timeout))
            return models_response

        monkeypatch.setattr(requests, "get", fake_get)
        return calls

    return install


def test_validate_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = validation.validate("openai")
    assert res["valid"] is False
    assert "error" in res
    assert res["error"]["error_type"] == "invalid_request"


def test_validate_unknown_provider():
    res = validation.validate("nope-not-real")
    assert res["valid"] is False
    assert res["error"]["error_type"] == "unsupported_capability"


def test_validate_invalid_format(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = validation.validate("openai", "not-a-real-format")
    assert res["valid"] is False
    assert res["error"]["error_type"] == "invalid_request"


def test_validate_success(monkeypatch, fake_requests):
    calls = fake_requests(FakeResponse(status_code=200, json_data={"data": []}))
    res = validation.validate("openai", "sk-validformat1234567890123456789012")
    assert res["valid"] is True
    assert res["authenticated"] is True
    assert "sk-validformat" not in str(res)


def test_validate_auth_failure(monkeypatch, fake_requests):
    fake_requests(FakeResponse(status_code=401, text="Invalid API key"))
    res = validation.validate("openai", "sk-badformat1234567890123456789012")
    assert res["valid"] is False
    assert res["error"]["error_type"] == "authentication"


def test_validate_rate_limit(monkeypatch, fake_requests):
    fake_requests(FakeResponse(status_code=429, text="Rate limit reached"))
    res = validation.validate("groq", "gsk_AbCdEfGhIjKlMnOpQrStUvWxYz1234")
    assert res["error"]["error_type"] == "rate_limited"
    assert res["error"]["retryable"] is True


def test_validate_provider_outage(monkeypatch, fake_requests):
    fake_requests(FakeResponse(status_code=503, text="down"))
    res = validation.validate("together", "tgp_v1_" + "A" * 60)
    assert res["error"]["error_type"] == "provider_outage"
    assert res["error"]["retryable"] is True


def test_validate_timeout(monkeypatch):
    def raise_timeout(url, headers=None, params=None, timeout=None):
        raise requests.Timeout("slow")

    monkeypatch.setattr(requests, "get", raise_timeout)
    res = validation.validate("openai", "sk-validformat1234567890123456789012")
    assert res["error"]["error_type"] == "timeout"
    assert res["error"]["retryable"] is True


def test_validate_network_error(monkeypatch):
    def raise_conn(url, headers=None, params=None, timeout=None):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", raise_conn)
    res = validation.validate("openai", "sk-validformat1234567890123456789012")
    assert res["error"]["error_type"] == "network_failure"


def test_validate_never_leaks_key_in_result(monkeypatch, fake_requests):
    key = "sk-supersecretkey1234567890123456789012"
    fake_requests(FakeResponse(status_code=200, json_data={"data": []}))
    res = validation.validate("openai", key)
    assert key not in str(res)
    # masked field shows only tail
    assert res["masked"].endswith(key[-4:])


def test_health_unsupported():
    h = validation.health_of("opencode")
    assert h["status"] == "unsupported"


def test_health_not_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    h = validation.health_of("anthropic")
    assert h["status"] == "not_configured"
    assert h["authenticated"] is False


def test_health_authenticated(monkeypatch, fake_requests):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-validformat1234567890123456789012")
    fake_requests(FakeResponse(status_code=200, json_data={"data": []}))
    h = validation.health_of("openai")
    assert h["status"] == "authenticated"
    assert h["authenticated"] is True


def test_unsupported_providers_cannot_validate():
    res = validation.validate("cursor")
    assert res["valid"] is False


def test_unknown_provider_alias_falls_back():
    assert isinstance(validation.health_of("gemini"), dict)