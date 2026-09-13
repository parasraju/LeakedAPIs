import json

import pytest

from api.cli import parse_args, run_keys, run_models, run_providers, run_validate


@pytest.fixture
def no_env_keys(monkeypatch):
    for v in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(v, raising=False)


def test_parse_providers():
    args = parse_args(["providers"])
    assert args.mode == "providers"
    assert args.json is False


def test_parse_providers_json():
    args = parse_args(["providers", "--json"])
    assert args.json is True


def test_parse_models_filter():
    args = parse_args(["models", "--provider", "openai"])
    assert args.provider == "openai"


def test_parse_models_alias():
    args = parse_args(["models", "--alias", "deepseek:reasoner"])
    assert args.alias == "deepseek:reasoner"


def test_parse_validate_provider():
    args = parse_args(["validate", "anthropic"])
    assert args.mode == "validate"
    assert args.provider == "anthropic"


def test_parse_keys():
    args = parse_args(["keys", "--json"])
    assert args.mode == "keys"
    assert args.json is True


def test_parse_services():
    args = parse_args(["services"])
    assert args.mode == "services"


def test_run_providers_lists_registry(capsys):
    run_providers(False)
    out = capsys.readouterr().out
    assert "openai" in out
    assert "anthropic" in out


def test_run_models_prints_header(capsys):
    run_models(parse_args(["models", "--provider", "openai"]))
    out = capsys.readouterr().out
    assert "gpt-4o" in out


def test_run_models_json(capsys):
    run_models(parse_args(["models", "--provider", "openai", "--json"]))
    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, list)
    assert all(m["provider"] == "openai" for m in data)


def test_run_validate_missing_key(no_env_keys, capsys):
    run_validate(parse_args(["validate", "openai", "--json"]))
    out = capsys.readouterr().out
    res = json.loads(out)
    assert res["valid"] is False
    assert "Missing API key" in res["message"]


def test_run_keys_masked(no_env_keys, capsys):
    run_keys(True)
    out = capsys.readouterr().out
    blob = json.loads(out)
    assert isinstance(blob, list)
    # browsers-heap style: none of them may include a raw-looking secret
    assert all(item.get("key", None) is None for item in blob)


def test_run_keys_never_prints_full_key(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abcdef0123456789abcdef0123456789")
    run_keys(False)
    out = capsys.readouterr().out
    assert "sk-abcdef0123456789abcdef0123456789" not in out
    assert "••" in out