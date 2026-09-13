"""Unified provider registry for API Instructor.

Provides central Provider dataclass and discovery functions.
Backward-compatible: SERVICES / PATTERNS remain in api.patterns.
"""

from .registry import (
    Provider,
    ProviderRegistry,
    get_provider,
    list_providers,
    provider_ids,
    register_provider,
)

from .catalog import PROVIDERS  # noqa: F401  triggers registration

__all__ = [
    "Provider",
    "ProviderRegistry",
    "get_provider",
    "list_providers",
    "provider_ids",
    "register_provider",
    "PROVIDERS",
]
