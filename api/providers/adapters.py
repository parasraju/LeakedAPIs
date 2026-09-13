"""OpenAI-compatible adapter and per-provider overrides.

Instead of duplicating logic for Groq/Together/OpenRouter/etc.,
this adapter handles request construction, auth headers, response
parsing and streaming uniformly.
"""

from __future__ import annotations

from typing import Any

import requests

from .registry import Provider, get_provider
from .errors import normalize_error


class OpenAICompatibleAdapter:
    """Reusable adapter for OpenAI-compatible providers."""

    def __init__(self, provider: Provider | str):
        if isinstance(provider, str):
            p = get_provider(provider)
            if not p:
                raise ValueError(f"Unknown provider: {provider}")
            provider = p
        self.provider = provider

    def headers(self, api_key: str) -> dict[str, str]:
        prov = self.provider
        if prov.auth_method == "bearer":
            return {"Authorization": f"Bearer {api_key}"}
        if prov.auth_method == "x-api-key":
            return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        if prov.auth_method == "api_key_header":
            return {prov.auth_header: api_key}
        if prov.auth_method == "query_param":
            return {}  # key goes in query string
        return {"Authorization": f"Bearer {api_key}"}

    def models_url(self) -> str:
        prov = self.provider
        if prov.models_endpoint and prov.models_endpoint.startswith("http"):
            return prov.models_endpoint
        if prov.models_endpoint:
            return prov.base_url.rstrip("/") + prov.models_endpoint
        # default OpenAI-style
        return prov.base_url.rstrip("/") + "/v1/models"

    def chat_url(self) -> str:
        return self.provider.base_url.rstrip("/") + "/chat/completions"

    def build_chat_request(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"model": model, "messages": messages}
        if stream:
            body["stream"] = True
        # pass through common params
        for k in ("temperature", "max_tokens", "top_p", "tools", "tool_choice", "response_format"):
            if k in kwargs and kwargs[k] is not None:
                body[k] = kwargs[k]
        return body

    def parse_models_response(self, data: dict) -> list[dict]:
        """Normalize /v1/models response to list of {id, object, created}."""
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return data["data"]
        if isinstance(data, list):
            return data
        return []

    def discover_models(self, api_key: str, timeout: int = 10) -> tuple[list[dict] | None, dict | None]:
        """GET /v1/models; returns (models, error)."""
        if not self.provider.supports_model_discovery:
            return None, {"error_type": "unsupported_capability", "message": "Model discovery not supported"}
        url = self.models_url()
        headers = self.headers(api_key)
        params = {}
        # Google-style query param auth
        if self.provider.auth_method == "query_param":
            # header is "query:key"
            qkey = self.provider.auth_header.split(":", 1)[1] if ":" in self.provider.auth_header else "key"
            params[qkey] = api_key
        try:
            r = requests.get(url, headers=headers, params=params or None, timeout=timeout)
        except requests.RequestException as e:
            return None, normalize_error(self.provider.id, e)
        if r.status_code != 200:
            return None, normalize_error(self.provider.id, r)
        try:
            data = r.json()
        except (ValueError, TypeError) as e:
            return None, normalize_error(self.provider.id, e, "Invalid JSON in models response")
        return self.parse_models_response(data), None

    def validate_credentials(self, api_key: str, timeout: int = 10) -> dict:
        """Minimal authenticated request to verify credentials."""
        if self.provider.status in ("unsupported", "unverified"):
            return {"provider": self.provider.id, "valid": False, "authenticated": False, "message": self.provider.description, "models_available": False}
        if self.provider.status == "special_auth":
            return {"provider": self.provider.id, "valid": False, "authenticated": False, "message": f"Special auth required: {self.provider.description}", "models_available": False}
        # Prefer models discovery if available (cheap GET)
        if self.provider.supports_model_discovery:
            models, err = self.discover_models(api_key, timeout=timeout)
            if err is None:
                return {"provider": self.provider.id, "valid": True, "authenticated": True, "message": "API key is valid", "models_available": True}
            # check if auth error vs other
            if err.get("error_type") == "authentication":
                return {"provider": self.provider.id, "valid": False, "authenticated": False, "message": "Authentication failed", "models_available": False, "error": err}
            if err.get("error_type") in ("rate_limited", "provider_outage", "timeout", "network_failure"):
                # ambiguous — treat as valid format but cannot confirm
                return {"provider": self.provider.id, "valid": True, "authenticated": False, "message": f"Key format accepted; verification inconclusive: {err.get('message')}", "models_available": False, "error": err}
            return {"provider": self.provider.id, "valid": False, "authenticated": False, "message": err.get("message", "Validation failed"), "models_available": False, "error": err}
        # fallback: try chat endpoint with invalid model to trigger auth check? avoid expensive; do basic format check
        if not api_key or len(api_key) < 8:
            return {"provider": self.provider.id, "valid": False, "authenticated": False, "message": "Missing or too short API key", "models_available": False}
        return {"provider": self.provider.id, "valid": True, "authenticated": False, "message": "Key format accepted (no discovery endpoint)", "models_available": False}


# Anthropic non-OpenAI adapter (example of override)
class AnthropicAdapter(OpenAICompatibleAdapter):
    def headers(self, api_key: str) -> dict[str, str]:  # type: ignore[override]
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}

    def chat_url(self) -> str:  # type: ignore[override]
        return self.provider.base_url.rstrip("/") + "/v1/messages"


def get_adapter(provider_id: str) -> OpenAICompatibleAdapter:
    p = get_provider(provider_id)
    if not p:
        raise ValueError(f"Unknown provider: {provider_id}")
    if p.id == "anthropic":
        return AnthropicAdapter(p)
    return OpenAICompatibleAdapter(p)
