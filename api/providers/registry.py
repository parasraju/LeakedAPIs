"""Provider registry — single source of truth for all AI/service providers."""

from __future__ import annotations

import dataclasses
from typing import Any

@dataclasses.dataclass
class Provider:
    """Declarative provider definition."""

    id: str  # slug, e.g. "openai"
    name: str  # human readable
    env_var: str  # primary API key env var
    base_url: str
    auth_method: str  # bearer | x-api-key | query_param | api_key_header | aws_sigv4 | gcp_oauth | none
    auth_header: str  # header name or "query:key" for query-param auth
    doc_url: str
    openai_compatible: bool = False
    supports_streaming: bool = False
    validation_endpoint: str | None = None
    validation_method: str = "GET"
    status: str = "active"  # active | deprecated | unsupported | special_auth | unverified
    description: str = ""
    aliases: list[str] = dataclasses.field(default_factory=list)
    extra_env_vars: list[str] = dataclasses.field(default_factory=list)
    capabilities: dict[str, Any] = dataclasses.field(default_factory=dict)
    # model discovery
    models_endpoint: str | None = None  # e.g. "/v1/models" relative or full URL
    # whether provider is discoverable via OpenAI-style GET /v1/models
    supports_model_discovery: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Provider.id is required")
        if not self.name:
            raise ValueError(f"Provider.name is required for '{self.id}'")
        if not self.env_var:
            raise ValueError(f"Provider.env_var is required for '{self.id}'")
        if self.status not in ("unsupported", "unverified"):
            if not self.base_url:
                raise ValueError(f"Provider.base_url is required for '{self.id}' (status={self.status})")
            if not self.doc_url:
                raise ValueError(f"Provider.doc_url is required for '{self.id}'")
        self.id = self.id.lower()
        self.env_var = self.env_var.strip()


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        pid = provider.id.lower()
        if pid in self._providers:
            raise ValueError(f"Duplicate provider id: {pid}")
        # also check duplicate env_var? warn only
        self._providers[pid] = provider
        # register aliases as lookup
        for alias in provider.aliases:
            al = alias.lower()
            if al != pid and al not in self._providers:
                # alias points to same object but not as primary key
                self._providers[al] = provider

    def get(self, provider_id: str) -> Provider | None:
        if not provider_id:
            return None
        return self._providers.get(provider_id.lower())

    def list(self, include_aliases: bool = False) -> list[Provider]:
        # deduplicate by id
        seen: set[str] = set()
        out: list[Provider] = []
        for p in self._providers.values():
            if p.id not in seen:
                seen.add(p.id)
                out.append(p)
        if not include_aliases:
            return out
        return list(self._providers.values())

    def ids(self) -> list[str]:
        return sorted({p.id for p in self._providers.values()})

    def clear(self) -> None:
        self._providers.clear()


_REGISTRY = ProviderRegistry()


def register_provider(provider: Provider) -> None:
    _REGISTRY.register(provider)


def get_provider(provider_id: str) -> Provider | None:
    return _REGISTRY.get(provider_id)


def list_providers() -> list[Provider]:
    return _REGISTRY.list()


def provider_ids() -> list[str]:
    return _REGISTRY.ids()


# get_masked_key moved to api.providers.keys for cohesion; keep a deprecated
# alias here so existing imports do not break.
from .keys import get_masked_key as get_masked_key  # noqa: F401  (back-compat re-export)
