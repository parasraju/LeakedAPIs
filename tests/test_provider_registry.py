import pytest

from api.providers import (
    PROVIDERS,
    Provider,
    ProviderRegistry,
    get_provider,
    list_providers,
    provider_ids,
    register_provider,
)
from api.providers.catalog import PROVIDERS as CATALOG


def _registry_with_seed():
    reg = ProviderRegistry()
    reg.register(
        Provider(
            id="openai",
            name="OpenAI",
            env_var="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            auth_method="bearer",
            auth_header="Authorization",
            doc_url="https://platform.openai.com/docs",
        )
    )
    return reg


def test_catalog_nonempty():
    assert len(CATALOG) > 10
    assert len(list_providers()) == len(CATALOG)


def test_core_providers_present():
    ids = set(provider_ids())
    for want in {
        "openai", "anthropic", "google", "xai", "deepseek", "mistral",
        "groq", "together", "openrouter", "fireworks", "perplexity",
        "cerebras", "sambanova", "deepinfra", "replicate", "huggingface",
        "cohere", "bedrock", "azure_openai", "vertex",
    }:
        assert want in ids, want


def test_all_providers_have_required_fields():
    for p in list_providers():
        assert p.id
        assert p.name
        assert p.env_var
        assert p.doc_url


def test_duplicate_provider_id_raises():
    reg = _registry_with_seed()
    with pytest.raises(ValueError):
        reg.register(
            Provider(
                id="openai",
                name="OpenAI Clone",
                env_var="OPENAI_API_KEY",
                base_url="https://x",
                auth_method="bearer",
                auth_header="Authorization",
                doc_url="https://x",
            )
        )


def test_register_and_get():
    reg = _registry_with_seed()
    p = reg.get("openai")
    assert p is not None
    assert p.name == "OpenAI"


def test_get_unknown_returns_none():
    assert get_provider("no-such-provider") is None


def test_invalid_provider_config_missing_base_url():
    reg = ProviderRegistry()
    with pytest.raises(ValueError):
        reg.register(  # noqa: F841
            Provider(
                id="bad",
                name="Bad",
                env_var="BAD_API_KEY",
                base_url="",
                auth_method="bearer",
                auth_header="Authorization",
                doc_url="",
            )
        )


def test_unsupported_coding_providers_marked_not_active():
    for pid in ("opencode", "cursor", "kiro"):
        p = get_provider(pid)
        assert p is not None
        assert p.status == "unsupported"


def test_aliases_resolve_to_same_provider():
    assert get_provider("gemini").id == "google"
    assert get_provider("hf").id == "huggingface"
    assert get_provider("google").id == "google"