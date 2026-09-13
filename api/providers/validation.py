"""Provider credential validation — common validate(provider, credentials) interface.

Combines key management (api.providers.keys) with the adapter's minimal
authenticated request. Returns a normalized result dict.
"""

from __future__ import annotations

import logging

import requests

from .adapters import get_adapter
from .errors import normalize_error
from .keys import format_is_valid, get_credentials, mask_key
from .registry import get_provider

logger = logging.getLogger(__name__)

# Local HTTP validator registry for providers that need a custom check.
# Keyed by provider id; value: callable(api_key, timeout) -> dict result.
SPECIAL_VALIDATORS: dict[str, callable] = {}


def register_validator(provider_id: str, fn: callable) -> None:
    SPECIAL_VALIDATORS[provider_id] = fn


def _basic_missing(key: str) -> bool:
    return not key or not key.strip()


def validate(provider_id: str, credentials: str | None = None, timeout: int = 10) -> dict:
    """Validate credentials for a provider.

    ``credentials`` falls back to environment variable for the provider.
    Returns normalized result never containing the raw key.
    """
    prov = get_provider(provider_id)
    if not prov:
        return {"provider": provider_id, "valid": False, "authenticated": False, "message": "Unknown provider", "models_available": False, "error": {"error_type": "unsupported_capability", "message": f"Unknown provider: {provider_id}", "retryable": False}}

    # Unsupported/special providers
    if prov.status in ("unsupported", "unverified"):
        return {"provider": prov.id, "valid": False, "authenticated": False, "message": prov.description or f"{prov.name} has no supported public API", "models_available": False}
    if prov.status == "special_auth":
        return {"provider": prov.id, "valid": False, "authenticated": False, "message": prov.description or f"{prov.name} requires special authentication (see env vars)", "models_available": False}

    if credentials is None:
        cred = get_credentials(prov.id)
        credentials = cred.key
        if not credentials:
            return {"provider": prov.id, "valid": False, "authenticated": False, "message": f"Missing API key (set {cred.env_var or prov.env_var})", "models_available": False, "error": {"error_type": "invalid_request", "message": "Missing API key", "retryable": False}}

    creds = credentials.strip()
    if _basic_missing(creds):
        return {"provider": prov.id, "valid": False, "authenticated": False, "message": "Missing API key", "models_available": False, "error": {"error_type": "invalid_request", "message": "Missing API key", "retryable": False}}

    if not format_is_valid(prov, creds):
        return {"provider": prov.id, "valid": False, "authenticated": False, "message": "API key does not match expected format", "models_available": False, "error": {"error_type": "invalid_request", "message": "Invalid key format", "retryable": False}}

    if prov.id in SPECIAL_VALIDATORS:
        try:
            result = SPECIAL_VALIDATORS[prov.id](creds, timeout=timeout)
        except Exception as e:  # noqa: BLE001 - arbitrary validator callables
            logger.warning("Special validator crashed for %s: %s", prov.id, e)
            result = {"provider": prov.id, "valid": False, "authenticated": False, "message": "Validation failed", "models_available": False}
        result.setdefault("provider", prov.id)
        return result

    try:
        adapter = get_adapter(prov.id)
    except ValueError as e:
        return {"provider": prov.id, "valid": False, "authenticated": False, "message": str(e), "models_available": False, "error": {"error_type": "unsupported_capability", "message": str(e), "retryable": False}}

    try:
        result = adapter.validate_credentials(creds, timeout=timeout)
    except requests.RequestException as e:
        err = normalize_error(prov.id, e)
        logger.warning("Validation request failed for %s: %s", prov.id, err.get("error_type"))
        result = {
            "provider": prov.id,
            "valid": False,
            "authenticated": False,
            "message": err.get("message", "Request failed"),
            "models_available": False,
            "error": err,
        }
    result["provider"] = prov.id
    result.setdefault("masked", mask_key(creds))
    return result


def validate_many(provider_ids: list[str] | None = None, timeout: int = 10) -> dict[str, dict]:
    from .registry import list_providers

    ids = provider_ids or [p.id for p in list_providers()]
    out: dict[str, dict] = {}
    for pid in ids:
        out[pid] = validate(pid, timeout=timeout)
    return out


def health_of(provider_id: str, prefer_cache: bool = True) -> dict:
    """Health/status summary for a provider, cached briefly to avoid expensive calls.

    Statuses: configured | authenticated | invalid_credentials | rate_limited
              unavailable | unsupported | not_configured
    """
    prov = get_provider(provider_id)
    if not prov:
        return {"provider": provider_id, "status": "unsupported", "authenticated": False, "models": 0}
    if prov.status in ("unsupported", "unverified"):
        return {"provider": prov.id, "status": "unsupported", "authenticated": False, "models": 0}
    if prov.status == "special_auth":
        return {"provider": prov.id, "status": "unsupported", "authenticated": False, "models": 0, "message": prov.description}

    cred = get_credentials(prov.id)
    if not cred.key:
        return {"provider": prov.id, "status": "not_configured", "authenticated": False, "models": 0, "env_var": cred.env_var}

    # count static + dynamic models quickly
    from .models import get_model_registry
    model_count = len(get_model_registry().models(prov.id))

    result = validate(prov.id)
    if result.get("valid"):
        if result.get("authenticated"):
            return {"provider": prov.id, "status": "authenticated", "authenticated": True, "models": model_count, "message": result.get("message")}
        return {"provider": prov.id, "status": "configured", "authenticated": False, "models": model_count, "message": result.get("message")}
    err = result.get("error") or {}
    etype = err.get("error_type", "invalid_credentials")
    if etype == "rate_limited":
        status = "rate_limited"
    elif etype in ("timeout", "network_failure", "provider_outage"):
        status = "unavailable"
    else:
        status = "invalid_credentials"
    return {"provider": prov.id, "status": status, "authenticated": False, "models": model_count, "message": result.get("message")}


def health_all() -> dict[str, dict]:
    from .registry import list_providers
    return {p.id: health_of(p.id) for p in list_providers()}