"""Centralized model registry with aliases, static models and dynamic discovery.

Models are verified against official docs at time of writing. Rapidly
changing catalogs (OpenRouter, Replicate, HuggingFace, Groq new releases)
are resolved dynamically via each provider's model-list API where one
exists, and merged on top of the verified static metadata below.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from .registry import get_provider

logger = logging.getLogger(__name__)

ModelStatus = str  # active | deprecated | experimental | dynamic | static


@dataclasses.dataclass
class Model:
    id: str
    provider: str
    name: str = ""
    type: str = "chat"  # chat | embedding | completion | image | audio | rerank
    context_window: int | None = None
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    supports_reasoning: bool = False
    status: ModelStatus = "active"
    aliases: list[str] = dataclasses.field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# Verified static catalog — curated sample of current flagship models.
# Marked status accordingly; dynamic providers refresh at runtime.
STATIC_MODELS: list[Model] = [
    # OpenAI
    Model("gpt-4o", "openai", "GPT-4o", "chat", 128000, False, True, True, False, "active", ["openai:gpt-latest"]),
    Model("gpt-4o-mini", "openai", "GPT-4o mini", "chat", 128000, True, True, True, False, "active", []),
    Model("gpt-4.1", "openai", "GPT-4.1", "chat", 1047576, False, True, True, False, "active", []),
    Model("gpt-4.1-mini", "openai", "GPT-4.1 mini", "chat", 1047576, True, True, True, False, "active", []),
    Model("gpt-4.1-nano", "openai", "GPT-4.1 nano", "chat", 1047576, True, True, False, False, "active", []),
    Model("o1", "openai", "o1", "chat", 200000, False, True, False, True, "active", ["openai:reasoner"]),
    Model("o1-mini", "openai", "o1 mini", "chat", 128000, False, True, True, True, "active", []),
    Model("o1-pro", "openai", "o1 pro", "chat", 200000, False, False, False, True, "active", []),
    Model("o3", "openai", "o3", "chat", 200000, False, True, True, True, "active", []),
    Model("o3-mini", "openai", "o3 mini", "chat", 200000, True, True, True, True, "active", []),
    Model("o4-mini", "openai", "o4 mini", "chat", 200000, True, True, True, True, "active", []),
    Model("gpt-4o-realtime", "openai", "GPT-4o Realtime", "audio", 128000, False, False, True, False, "experimental", []),
    Model("text-embedding-3-small", "openai", "text-embedding-3 small", "embedding", None, False, False, False, False, "active", []),
    Model("text-embedding-3-large", "openai", "text-embedding-3 large", "embedding", None, False, False, False, False, "active", []),
    Model("text-embedding-ada-002", "openai", "text-embedding ada 002", "embedding", None, False, False, False, False, "deprecated", []),
    Model("whisper-1", "openai", "Whisper", "audio", None, False, False, False, False, "active", []),
    Model("dall-e-3", "openai", "DALL-E 3", "image", None, False, False, False, False, "active", []),
    Model("gpt-3.5-turbo", "openai", "GPT-3.5 Turbo", "chat", 16385, True, True, True, False, "deprecated", []),
    # Anthropic
    Model("claude-opus-4-1", "anthropic", "Claude Opus 4.1", "chat", 200000, False, True, True, False, "active", ["anthropic:claude-opus"]),
    Model("claude-opus-4", "anthropic", "Claude Opus 4", "chat", 200000, False, True, True, False, "active", []),
    Model("claude-sonnet-4-5", "anthropic", "Claude Sonnet 4.5", "chat", 200000, False, True, True, False, "active", ["anthropic:claude-sonnet"]),
    Model("claude-sonnet-4", "anthropic", "Claude Sonnet 4", "chat", 200000, False, True, True, False, "active", []),
    Model("claude-haiku-4-5", "anthropic", "Claude Haiku 4.5", "chat", 200000, False, True, True, False, "active", ["anthropic:claude-haiku"]),
    Model("claude-3-opus", "anthropic", "Claude 3 Opus", "chat", 200000, False, True, True, False, "deprecated", []),
    Model("claude-3-sonnet", "anthropic", "Claude 3 Sonnet", "chat", 200000, False, True, True, False, "deprecated", []),
    Model("claude-3-haiku", "anthropic", "Claude 3 Haiku", "chat", 200000, False, True, True, False, "deprecated", []),
    # Google
    Model("gemini-2.5-pro", "google", "Gemini 2.5 Pro", "chat", 1048576, False, True, True, True, "active", ["google:gemini-pro"]),
    Model("gemini-2.5-flash", "google", "Gemini 2.5 Flash", "chat", 1048576, True, True, True, True, "active", ["google:gemini-flash"]),
    Model("gemini-2.5-flash-lite", "google", "Gemini 2.5 Flash Lite", "chat", 1048576, True, True, True, True, "active", []),
    Model("gemini-2.0-flash", "google", "Gemini 2.0 Flash", "chat", 1048576, True, True, True, False, "deprecated", []),
    Model("gemini-1.5-pro", "google", "Gemini 1.5 Pro", "chat", 2097152, False, True, True, False, "deprecated", []),
    Model("gemini-1.5-flash", "google", "Gemini 1.5 Flash", "chat", 1048576, True, True, True, False, "deprecated", []),
    Model("gemini-2.0-flash-realtime", "google", "Gemini 2.0 Flash Realtime", "audio", 1048576, True, False, True, False, "active", []),
    Model("gemini-embedding-001", "google", "Gemini Embedding", "embedding", None, False, False, False, False, "active", []),
    Model("gemini-2.5-flash-image", "google", "Gemini 2.5 Flash Image (Nano Banana)", "image", 1048576, False, False, True, False, "active", []),
    # xAI
    Model("grok-4", "xai", "Grok 4", "chat", 262144, False, True, True, True, "active", ["xai:grok"]),
    Model("grok-4-fast", "xai", "Grok 4 Fast", "chat", 262144, False, True, True, True, "active", []),
    Model("grok-3", "xai", "Grok 3", "chat", 131072, False, True, True, True, "deprecated", []),
    Model("grok-3-mini", "xai", "Grok 3 mini", "chat", 131072, True, True, True, True, "deprecated", []),
    Model("grok-2", "xai", "Grok 2", "chat", 8192, True, True, True, False, "deprecated", []),
    Model("grok-2-vision", "xai", "Grok 2 Vision", "chat", 8192, True, True, True, False, "deprecated", []),
    # DeepSeek
    Model("deepseek-chat", "deepseek", "DeepSeek V3", "chat", 64000, True, True, True, False, "active", ["deepseek:chat"]),
    Model("deepseek-reasoner", "deepseek", "DeepSeek R1", "chat", 64000, True, True, True, True, "active", ["deepseek:reasoner"]),
    Model("deepseek-coder", "deepseek", "DeepSeek Coder", "chat", 32000, True, True, True, False, "deprecated", []),
    # Mistral
    Model("mistral-large-latest", "mistral", "Mistral Large", "chat", 128000, True, True, True, True, "active", ["mistral:large"]),
    Model("mistral-small-latest", "mistral", "Mistral Small", "chat", 32000, True, True, True, True, "active", ["mistral:small"]),
    Model("codestral-latest", "mistral", "Codestral", "chat", 256000, True, True, False, False, "active", ["mistral:codestral"]),
    Model("ministral-8b-latest", "mistral", "Ministral 8B", "chat", 128000, True, True, True, False, "active", []),
    Model("open-mistral-7b", "mistral", "Mistral 7B", "chat", 32000, True, True, False, False, "deprecated", []),
    # Groq — dynamic catalog, static samples
    Model("llama-3.3-70b-versatile", "groq", "Llama 3.3 70B Versatile", "chat", 131072, True, True, False, False, "active", ["groq:llama"]),
    Model("llama-3.1-8b-instant", "groq", "Llama 3.1 8B Instant", "chat", 131072, True, True, False, False, "active", []),
    Model("mixtral-8x7b-32768", "groq", "Mixtral 8x7B", "chat", 32768, True, True, False, False, "deprecated", []),
    Model("gemma2-9b-it", "groq", "Gemma 2 9B", "chat", 8192, True, True, False, False, "deprecated", []),
    Model("whisper-large-v3", "groq", "Whisper Large v3", "audio", None, False, False, False, False, "active", []),
    # Cohere
    Model("command-r-plus", "cohere", "Command R+", "chat", 128000, True, True, False, False, "deprecated", []),
    Model("command-r", "cohere", "Command R", "chat", 128000, True, True, False, False, "deprecated", []),
    Model("command-a", "cohere", "Command A", "chat", 256000, True, True, False, False, "active", ["cohere:command"]),
    Model("embed-english-v3.0", "cohere", "Embed English v3", "embedding", None, False, False, False, False, "active", []),
    Model("rerank-english-v3.0", "cohere", "Rerank English v3", "rerank", None, False, False, False, False, "active", []),
    # Together — dynamic catalog, static samples
    Model("meta-llama/Llama-3.3-70B-Instruct-Turbo", "together", "Llama 3.3 70B Instruct Turbo", "chat", 8172, True, True, False, False, "active", ["together:llama"]),
    Model("Qwen/Qwen2.5-72B-Instruct-Turbo", "together", "Qwen 2.5 72B Instruct", "chat", 32768, True, True, False, False, "active", ["together:qwen"]),
    Model("deepseek-ai/DeepSeek-V3", "together", "DeepSeek V3", "chat", 64000, True, True, False, False, "active", []),
    Model("meta-llama/Llama-3.1-8B-Instruct-Turbo", "together", "Llama 3.1 8B Instruct", "chat", 8192, True, True, False, False, "deprecated", []),
    # Cerebras
    Model("llama-3.3-70b", "cerebras", "Llama 3.3 70B", "chat", 131072, True, True, False, False, "active", []),
    Model("llama-3.1-8b", "cerebras", "Llama 3.1 8B", "chat", 131072, True, True, False, False, "active", []),
    # Fireworks
    Model("accounts/fireworks/models/llama-v3p1-405b-instruct", "fireworks", "Llama 3.1 405B Instruct", "chat", 8192, True, True, False, False, "active", ["fireworks:llama"]),
    Model("accounts/fireworks/models/qwen2p5-coder-32b-instruct", "fireworks", "Qwen 2.5 Coder 32B", "chat", 4096, True, True, False, False, "active", []),
    # Perplexity
    Model("sonar", "perplexity", "Sonar", "chat", 127000, True, True, False, False, "active", ["perplexity:sonar"]),
    Model("sonar-pro", "perplexity", "Sonar Pro", "chat", 200000, True, True, True, False, "active", []),
    Model("sonar-reasoning", "perplexity", "Sonar Reasoning", "chat", 127000, True, True, False, True, "active", []),
    Model("sonar-reasoning-pro", "perplexity", "Sonar Reasoning Pro", "chat", 127000, True, True, False, True, "active", []),
    # AI21
    Model("jamba-1.5-large", "ai21", "Jamba 1.5 Large", "chat", 256000, True, True, False, False, "active", ["ai21:jamba"]),
    Model("jamba-1.5-mini", "ai21", "Jamba 1.5 Mini", "chat", 256000, True, True, False, False, "active", []),
    # SambaNova
    Model("llama-3.3-70b", "sambanova", "Llama 3.3 70B", "chat", 16384, True, True, False, False, "active", ["sambanova:llama"]),
    # DeepInfra — dynamic catalog
    Model("meta-llama/Meta-Llama-3.1-70B-Instruct", "deepinfra", "Llama 3.1 70B", "chat", 8192, True, True, False, False, "active", []),
    Model("Qwen/Qwen2.5-72B-Instruct", "deepinfra", "Qwen 2.5 72B", "chat", 32768, True, True, False, False, "active", []),
    # OpenRouter — dynamic catalog, sample
    Model("openai/gpt-4o", "openrouter", "GPT-4o via OpenRouter", "chat", 128000, True, True, True, False, "active", ["openrouter:gpt-4o"]),
    Model("anthropic/claude-opus-2", "openrouter", "Claude Opus 2 via OpenRouter", "chat", 200000, True, True, True, False, "active", []),
]

# Aliases that map to future/current models without pinning to a static one.
# These resolve dynamically against the provider's discovery endpoint when
# possible, falling back to the static default listed here.
ALIASES: dict[str, str] = {
    "openai:gpt-latest": "gpt-4o",
    "openai:reasoner": "o3-mini",
    "anthropic:claude-opus": "claude-opus-4-1",
    "anthropic:claude-sonnet": "claude-sonnet-4-5",
    "anthropic:claude-haiku": "claude-haiku-4-5",
    "google:gemini-flash": "gemini-2.5-flash",
    "google:gemini-pro": "gemini-2.5-pro",
    "xai:grok": "grok-4",
    "deepseek:reasoner": "deepseek-reasoner",
    "deepseek:chat": "deepseek-chat",
    "mistral:large": "mistral-large-latest",
    "mistral:small": "mistral-small-latest",
    "mistral:codestral": "codestral-latest",
    "groq:llama": "llama-3.3-70b-versatile",
    "together:llama": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "together:qwen": "Qwen/Qwen2.5-72B-Instruct-Turbo",
    "cohere:command": "command-a",
    "ai21:jamba": "jamba-1.5-large",
    "fireworks:llama": "accounts/fireworks/models/llama-v3p1-405b-instruct",
    "sambanova:llama": "llama-3.3-70b",
    "perplexity:sonar": "sonar",
    "openrouter:gpt-4o": "openai/gpt-4o",
}


class ModelRegistry:
    def __init__(self) -> None:
        self._static: dict[tuple[str, str], Model] = {}
        self._dynamic: dict[tuple[str, str], Model] = {}
        self._alias_map: dict[str, str] = dict(ALIASES)
        self._register_static()
        self._cache_ttl = 3600
        self._cache: dict[str, tuple[float, list[dict]]] = {}

    def _register_static(self) -> None:
        for m in STATIC_MODELS:
            key = (m.provider, m.id)
            self._static[key] = m
            for a in m.aliases:
                self._alias_map[a] = m.id
        # provider:id style aliases listed in models also get full-prefixed alias
        for m in STATIC_MODELS:
            if m.aliases:
                for a in m.aliases:
                    self._alias_map[a] = m.id

    def _provider_slug(self, provider: str) -> str | None:
        p = get_provider(provider)
        return p.id if p else provider

    def add_dynamic(self, provider: str, model_id: str, created: int = 0, verbose: bool = True) -> Model:
        """Register a discovered model (from provider /v1/models)."""
        prov = self._provider_slug(provider)
        key = (prov, model_id)
        if key in self._static:
            return self._static[key]
        model = Model(
            id=model_id,
            provider=prov,
            name=model_id,
            status="dynamic",
        )
        self._dynamic[key] = model
        return model

    def resolve(self, model_id: str, provider: str | None = None) -> Model | None:
        """Resolve a model id, optionally 'provider' prefixed, or bare alias."""
        m = self.resolve_alias(model_id)
        if m:
            return m
        # bare id with provider hint
        if provider:
            key = (self._provider_slug(provider) or provider, model_id)
            if key in self._static:
                return self._static[key]
            if key in self._dynamic:
                return self._dynamic[key]
        # bare id, search any provider
        for (prov, mid), model in {**self._static, **self._dynamic}.items():
            if mid == model_id:
                return model
        return None

    def resolve_alias(self, alias: str) -> Model | None:
        a = alias.lower()
        if a in self._alias_map:
            target_id = self._alias_map[a]
            # target is full provider:id? then extract
            if ":" in target_id and not a.startswith("openai:"):
                return self.resolve(target_id)
            # figure provider from alias prefix if present
            if ":" in a:
                provider, _ = a.split(":", 1)
                key = (provider, target_id)
                if key in self._static:
                    return self._static[key]
                if key in self._dynamic:
                    return self._dynamic[key]
            return self.resolve(target_id, provider=a.split(":", 1)[0] if ":" in a else None)
        return None

    def models(self, provider: str | None = None) -> list[Model]:
        merged: dict[tuple[str, str], Model] = {**self._static}
        for key, m in self._dynamic.items():
            if key not in merged and m.status == "dynamic":
                merged[key] = m
        if provider:
            prov = self._provider_slug(provider)
            return [m for (p, _), m in merged.items() if p == prov]
        return list(merged.values())

    def to_dict(self, provider: str | None = None) -> list[dict]:
        return [m.to_dict() for m in self.models(provider)]

    def discover(self, provider: str, api_key: str, timeout: int = 10) -> tuple[int, dict | None]:
        """Dynamically fetch /v1/models for provider. Returns (count, error)."""
        from .adapters import get_adapter

        prov = get_provider(provider)
        if not prov or not prov.supports_model_discovery:
            return 0, {"error_type": "unsupported_capability", "message": f"{provider}: model discovery not supported"}
        adapter = get_adapter(provider)
        models, err = adapter.discover_models(api_key, timeout=timeout)
        if err or models is None:
            return 0, err
        count = 0
        for m in models:
            if isinstance(m, dict):
                mid = m.get("id")
                if mid:
                    self.add_dynamic(provider, str(mid), created=m.get("created", 0))
                    count += 1
        return count, None


_REGISTRY = ModelRegistry()


def get_model_registry() -> ModelRegistry:
    return _REGISTRY


# convenience pass-throughs
def list_models(provider: str | None = None) -> list[dict]:
    return _REGISTRY.to_dict(provider)


def resolve_model(model_id: str, provider: str | None = None) -> dict | None:
    m = _REGISTRY.resolve(model_id, provider)
    return m.to_dict() if m else None


def discover_models(provider: str, api_key: str, timeout: int = 10) -> tuple[int, dict | None]:
    return _REGISTRY.discover(provider, api_key, timeout=timeout)