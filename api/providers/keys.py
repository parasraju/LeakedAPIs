"""Secure API-key configuration management.

Reads keys from environment variables. Provides masking utilities to
prevent secret leakage in logs, errors or API responses.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .registry import Provider, get_provider, list_providers

# Common key shape assertions, per provider where they exist.
# These are structural checks only — never enough to authenticate.
_KEY_FORMAT_HINTS: dict[str, re.Pattern] = {
    "openai": re.compile(r"^sk-(proj-[A-Za-z0-9]{20,}|[A-Za-z0-9]{20,})"),
    "anthropic": re.compile(r"^sk-ant-[A-Za-z0-9]{20,}"),
    "google": re.compile(r"^AIza[0-9A-Za-z_-]{35}$"),
    "xai": re.compile(r"^xai-[A-Za-z0-9]{20,}"),
    "deepseek": re.compile(r"^sk-[A-Za-z0-9]{20,}"),
    "mistral": re.compile(r"^[A-Za-z0-9]{32}$"),
    "groq": re.compile(r"^gsk_[A-Za-z0-9]{20,}"),
    "together": re.compile(r"^(tgp_v1_)?[A-Za-z0-9]{50,}"),
    "openrouter": re.compile(r"^sk-or-v1-[A-Za-z0-9]{20,}"),
    "fireworks": re.compile(r"^[A-Za-z0-9]{25,}"),
    "perplexity": re.compile(r"^pplx-[A-Za-z0-9]{30,}"),
    "cerebras": re.compile(r"^csk-[A-Za-z0-9]{20,}"),
    "cohere": re.compile(r"^[A-Za-z0-9]{40,}"),
    "huggingface": re.compile(r"^hf_[A-Za-z0-9]{20,}"),
    "replicate": re.compile(r"^r8_[A-Za-z0-9]{20,}"),
    "sambanova": re.compile(r"^[A-Za-z0-9]{60,}"),
    "deepinfra": re.compile(r"^[A-Za-z0-9]{30,}"),
}


def mask_key(key: str | None, head: int = 3, tail: int = 4) -> str:
    """Mask a key for display: ``sk-••••••••••••••••1234``."""
    if not key:
        return "not configured"
    key = key.strip()
    if len(key) <= head + tail:
        return "•" * len(key)
    return f"{key[:head]}••••••••••••••••{key[-tail:]}"


def get_masked_key(provider_id: str, key: str | None = None) -> str:
    """Masked display form of a provider key (from arg or environment)."""
    if key is None:
        return get_credentials(provider_id).masked
    return mask_key(key)


def redact(value: str, keep_head: int = 3, keep_tail: int = 4, threshold: int = 8) -> str:
    """Redact any string that looks like a secret (long token/pattern prefixes)."""
    if not value:
        return value
    # guard against leaking in error messages
    if len(value) >= threshold and not value.startswith(("http", "/", ".", "-")):
        return mask_key(value, keep_head, keep_tail)
    return value


@dataclass
class ProviderCredentials:
    provider: str
    key: str | None = None
    env_var: str = ""
    masked: str = "not configured"
    status: str = "not_configured"  # configured | valid | invalid_credentials | rate_limited | unavailable
    format_valid: bool = False

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "env_var": self.env_var,
            "configured": self.key is not None,
            "status": self.status,
            "masked": self.masked,
            "format_valid": self.format_valid,
        }


def _first_env(env_vars: list[str]) -> tuple[str, str]:
    """Return (env_var, value) of first non-empty env var in list."""
    for v in env_vars:
        val = os.environ.get(v, "").strip()
        if val:
            return v, val
    return (env_vars[0], "") if env_vars else ("", "")


def format_is_valid(provider: Provider, key: str) -> bool:
    pat = _KEY_FORMAT_HINTS.get(provider.id, _KEY_FORMAT_HINTS.get(getattr(provider, "id", "")))
    if pat:
        return bool(pat.match(key.strip()))
    return len(key) >= 8


def get_credentials(provider_id: str) -> ProviderCredentials:
    """Read credentials for provider from environment without exposing key."""
    prov = get_provider(provider_id)
    if not prov:
        return ProviderCredentials(provider=provider_id, status="unsupported", masked="unknown provider")
    env_vars = [prov.env_var] + [e for e in prov.extra_env_vars]
    env_var, value = _first_env(env_vars)
    if not value:
        return ProviderCredentials(provider=prov.id, env_var=env_var, status="not_configured")
    masked = mask_key(value)
    fmt = format_is_valid(prov, value)
    status = "configured" if fmt else "invalid_credentials"
    return ProviderCredentials(provider=prov.id, key=value, env_var=env_var, masked=masked, status=status, format_valid=fmt)


def all_credentials() -> dict[str, dict]:
    return {p.id: get_credentials(p.id).to_dict() for p in list_providers()}


def configured_providers() -> list[str]:
    return [p.id for p in list_providers() if get_credentials(p.id).key]

def get_api_key(provider_id: str) -> str | None:
    """Return the raw key only for direct adapter use; never log/display."""
    return get_credentials(provider_id).key