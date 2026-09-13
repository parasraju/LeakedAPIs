import pytest
import requests

from api.providers.models import (
    ALIASES,
    STATIC_MODELS,
    Model,
    ModelRegistry,
    get_model_registry,
    list_models,
    resolve_model,
)
from api.providers.registry import get_provider


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json


def test_static_catalog_populated():
    assert len(STATIC_MODELS) > 30
    providers = {m.provider for m in STATIC_MODELS}
    assert {"openai", "anthropic", "google", "xai", "deepseek", "mistral"} <= providers


def test_model_dict_schema():
    m = Model("gpt-4o", "openai", type="chat")
    d = m.to_dict()
    assert d["id"] == "gpt-4o"
    assert d["provider"] == "openai"
    assert "status" in d and "supports_streaming" in d


def test_resolve_by_provider_and_id():
    m = get_model_registry().resolve("gpt-4o", provider="openai")
    assert m is not None and m.id == "gpt-4o"


def test_resolve_bare_id():
    m = get_model_registry().resolve("claude-opus-4-1")
    assert m is not None and m.provider == "anthropic"


def test_resolve_unknown_returns_none():
    assert get_model_registry().resolve("no-such-model-xyz") is None


def test_aliases_resolve():
    reg = get_model_registry()
    for alias in ALIASES:
        assert reg.resolve_alias(alias) is not None, alias


def test_alias_named_in_task():
    reg = get_model_registry()
    for alias in ("openai:gpt-latest", "anthropic:claude-sonnet", "google:gemini-flash",
                  "deepseek:reasoner", "xai:grok"):
        assert reg.resolve_alias(alias) is not None, alias
        # alias must resolve within the stated provider
        assert reg.resolve_alias(alias).provider == alias.split(":", 1)[0]


def test_deprecated_models_marked():
    assert get_model_registry().resolve("gpt-3.5-turbo").status == "deprecated"
    assert get_model_registry().resolve("claude-3-opus").status == "deprecated"


def test_dynamic_add_and_status():
    reg = ModelRegistry()
    reg.add_dynamic("openai", "gpt-9999-super")
    assert reg.resolve("gpt-9999-super", provider="openai").status == "dynamic"
    assert reg.resolve("gpt-9999-super", provider="openai").provider == "openai"


def test_discovery_success(monkeypatch):
    reg = ModelRegistry()

    def fake_get(url, headers=None, params=None, timeout=None):
        return FakeResponse(200, json_data={"data": [{"id": "gpt-dynamic-1"}, {"id": "gpt-dynamic-2"}]})

    monkeypatch.setattr(requests, "get", fake_get)
    count, err = reg.discover("openai", "sk-test1234567890123456789012345678")
    assert err is None
    assert count == 2
    assert reg.resolve("gpt-dynamic-1", provider="openai") is not None


def test_discovery_auth_error(monkeypatch):
    reg = ModelRegistry()

    def fake_get(url, headers=None, params=None, timeout=None):
        return FakeResponse(401, text="bad key")

    monkeypatch.setattr(requests, "get", fake_get)
    count, err = reg.discover("openai", "sk-test1234567890123456789012345678")
    assert count == 0
    assert err["error_type"] == "authentication"


def test_discovery_skipped_for_unsupported_provider():
    reg = ModelRegistry()
    count, err = reg.discover("replicate", "r8_test1234567890123456")
    assert count == 0
    assert err["error_type"] == "unsupported_capability"


def test_discover_modules_pass_through():
    assert isinstance(list_models("openai"), list)
    m = resolve_model("gemini-2.5-flash")
    assert m and m["provider"] == "google"


def test_no_hardcoded_model_specs_where_dynamic():
    p = get_provider("openrouter")
    assert p.supports_model_discovery is True