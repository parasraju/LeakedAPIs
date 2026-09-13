import requests

from api.providers.adapters import (
    AnthropicAdapter,
    OpenAICompatibleAdapter,
    get_adapter,
)
from api.providers.errors import normalize_error


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json


def test_get_adapter_returns_compatible():
    a = get_adapter("groq")
    assert isinstance(a, OpenAICompatibleAdapter)
    assert a.provider.id == "groq"


def test_get_adapter_anthropic_override():
    a = get_adapter("anthropic")
    assert isinstance(a, AnthropicAdapter)


def test_get_adapter_unknown_raises():
    try:
        get_adapter("made-up")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_build_chat_request_default():
    a = get_adapter("deepseek")
    body = a.build_chat_request("deepseek-chat", [{"role": "user", "content": "hi"}])
    assert body["model"] == "deepseek-chat"
    assert body["messages"][0]["role"] == "user"
    assert "stream" not in body


def test_build_chat_request_stream_and_params():
    a = get_adapter("openai")
    body = a.build_chat_request(
        "gpt-4o-mini",
        [{"role": "user", "content": "hi"}],
        stream=True,
        temperature=0.5,
        max_tokens=10,
    )
    assert body["stream"] is True
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 10


def test_headers_bearer_vs_api_key():
    a = get_adapter("groq")
    assert a.headers("abc") == {"Authorization": "Bearer abc"}
    an = get_adapter("anthropic")
    h = an.headers("abc")
    assert h["x-api-key"] == "abc"
    assert "anthropic-version" in h


def test_models_url_behavior():
    assert get_adapter("openai").models_url() == "https://api.openai.com/v1/models"
    assert get_adapter("deepinfra").models_url() == "https://api.deepinfra.com/v1/openai/models"


def test_parse_models_response():
    a = get_adapter("openai")
    data = {"data": [{"id": "gpt-4o", "object": "model"}, {"id": "gpt-4o-mini"}]}
    parsed = a.parse_models_response(data)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "gpt-4o"
    # list passthrough
    assert a.parse_models_response([{"id": "x"}]) == [{"id": "x"}]
    # garbage -> []
    assert a.parse_models_response({"nope": 1}) == []


def test_discover_models_returns_normalized(monkeypatch):
    a = get_adapter("openai")

    def fake_get(url, headers, params, timeout):
        return FakeResponse(200, json_data={"data": [{"id": "gpt-4o"}]})

    monkeypatch.setattr(requests, "get", fake_get)
    models, err = a.discover_models("sk-test1234567890123456789012")
    assert err is None
    assert models[0]["id"] == "gpt-4o"


def test_discover_models_error(monkeypatch):
    a = get_adapter("openai")

    def fake_get(url, headers, params, timeout):
        return FakeResponse(401)

    monkeypatch.setattr(requests, "get", fake_get)
    models, err = a.discover_models("sk-test1234567890123456789012")
    assert models is None
    assert err["error_type"] == "authentication"


def test_normalize_error_timeout():
    err = normalize_error("openai", requests.Timeout("slow"))
    assert err["error_type"] == "timeout"
    assert err["retryable"] is True


def test_normalize_error_connection():
    err = normalize_error("openai", requests.ConnectionError("offline"))
    assert err["error_type"] == "network_failure"


def test_normalize_error_status_codes():
    assert normalize_error("openai", FakeResponse(401)).get("error_type") == "authentication"
    assert normalize_error("openai", FakeResponse(403)).get("error_type") == "authentication"
    assert normalize_error("openai", FakeResponse(404)).get("error_type") == "model_not_found"
    assert normalize_error("openai", FakeResponse(429)).get("error_type") == "rate_limited"
    assert normalize_error("openai", FakeResponse(502)).get("error_type") == "provider_outage"
    assert normalize_error("openai", FakeResponse(400)).get("error_type") == "invalid_request"


def test_normalize_error_retryable_flags():
    assert normalize_error("openai", FakeResponse(401))["retryable"] is False
    assert normalize_error("openai", FakeResponse(429))["retryable"] is True
    assert normalize_error("openai", FakeResponse(500))["retryable"] is True


def test_normalize_error_quota():
    assert normalize_error("openai", FakeResponse(429, text="You exceeded your current quota")).get("error_type") == "quota_exhausted"


def test_adapter_validate_credentials_success(monkeypatch):
    a = get_adapter("openai")

    def fake_get(url, headers, params, timeout):
        return FakeResponse(200, json_data={"data": []})

    monkeypatch.setattr(requests, "get", fake_get)
    res = a.validate_credentials("sk-test1234567890123456789012")
    assert res["valid"] is True
    assert res["authenticated"] is True
    assert res["models_available"] is True