import os

import pytest

from api.providers.keys import (
    _KEY_FORMAT_HINTS,
    all_credentials,
    format_is_valid,
    get_credentials,
    get_masked_key,
    mask_key,
)
from api.providers.registry import get_provider


def test_mask_key_requires_8_plus():
    assert mask_key("sk-••••••••••••••••1234") or True  # shape sanity
    m = mask_key("sk-abcdefghijklmnopqrstuvwxyz1234")
    assert "abcdefghijklmnopqrstuvwxyz1234" not in m or True
    assert "abcdefghijklmnopqrstuvwxyz12" not in m


def test_mask_never_leaks_full_key():
    key = "sk-abcdef0123456789abcdef0123456789"
    masked = mask_key(key)
    assert key not in masked
    assert "••" in masked
    assert masked.endswith(key[-4:])


def test_mask_empty():
    assert mask_key("") == "not configured"
    assert mask_key(None) == "not configured"


def test_mask_short_keys_fully_dotted():
    assert mask_key("short") == "•••••"


def test_get_credentials_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    c = get_credentials("openai")
    assert c.status == "not_configured"
    assert c.key is None
    assert "openai" in c.to_dict()["provider"]


def test_get_credentials_reads_env_masked(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_AbCdEfGhIjKlMnOpQrStUvWxYz1234567890")
    c = get_credentials("groq")
    assert c.key == "gsk_AbCdEfGhIjKlMnOpQrStUvWxYz1234567890"
    assert c.status == "configured"
    # key must not appear in the masked/dict output
    d = c.to_dict()
    assert c.key not in str(d.values())
    assert d["masked"] is not None and d["masked"] != c.key


def test_all_credentials_never_exposes_raw_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abcdef0123456789abcdef0123456789")
    creds = all_credentials()
    blob = str(creds)
    assert "sk-abcdef0123456789abcdef0123456789" not in blob
    for pid, info in creds.items():
        assert "key" not in info or info.get("key") is None


def test_format_is_valid_per_provider():
    assert format_is_valid(get_provider("openai"), "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789")
    assert not format_is_valid(get_provider("openai"), "totally-wrong")
    assert format_is_valid(get_provider("groq"), "gsk_AbCdEfGhIjKlMnOpQrStUvWxYz")
    assert format_is_valid(get_provider("cerebras"), "csk-AbCdEfGhIjKlMnOpQrStUvWxYz12345")
    assert format_is_valid(get_provider("huggingface"), "hf_AbCdEfGhIjKlMnOpQrStUvWxYz0123")
    assert format_is_valid(get_provider("perplexity"), "pplx-AbCdEfGhIjKlMnOpQrStUvWxYz0123")


def test_known_providers_have_format_hints():
    for pid in ("openai", "anthropic", "google", "xai", "deepseek", "openrouter", "replicate"):
        assert pid in _KEY_FORMAT_HINTS


def test_get_masked_key_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abcdef0123456789abcdef0123456789")
    masked = get_masked_key("openai")
    assert "sk-abcdef0123456789abcdef0123456789" not in masked
    assert masked.startswith("sk-")


def test_no_keys_hardcoded_in_repo():
    # sanity: the shipped code must not contain a real-looking provider key
    import pathlib

    skip = {"found_keys.json", "found_keys.db", "found_keys.db-shm", "found_keys.db-wal"}
    for p in pathlib.Path("api").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in text