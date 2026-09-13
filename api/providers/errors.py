"""Normalized error handling for all providers."""

from __future__ import annotations

import requests


ERROR_TYPES = {
    "authentication",
    "rate_limited",
    "quota_exhausted",
    "model_not_found",
    "invalid_request",
    "provider_outage",
    "timeout",
    "network_failure",
    "unsupported_capability",
    "unknown",
}


def _is_response(obj) -> bool:
    return hasattr(obj, "status_code") and hasattr(obj, "text")


def normalize_error(provider: str, exc: Exception | requests.Response | None, message: str = "") -> dict:
    """Convert any error into unified format."""
    if isinstance(exc, requests.Timeout):
        return {
            "provider": provider,
            "error_type": "timeout",
            "message": message or "Request timed out",
            "retryable": True,
            "status_code": None,
        }
    if isinstance(exc, requests.ConnectionError):
        return {
            "provider": provider,
            "error_type": "network_failure",
            "message": message or "Network failure",
            "retryable": True,
            "status_code": None,
        }
    if _is_response(exc):
        sc = exc.status_code
        text = (exc.text or "")[:300]
        if sc == 401:
            return {"provider": provider, "error_type": "authentication", "message": message or f"Authentication failed: {text}", "retryable": False, "status_code": sc}
        if sc == 403:
            return {"provider": provider, "error_type": "authentication", "message": message or f"Forbidden: {text}", "retryable": False, "status_code": sc}
        if sc == 404:
            return {"provider": provider, "error_type": "model_not_found", "message": message or f"Not found: {text}", "retryable": False, "status_code": sc}
        if sc in (402, 429) and "quota" in text.lower():
            return {"provider": provider, "error_type": "quota_exhausted", "message": message or "Quota exhausted", "retryable": True, "status_code": sc}
        if sc == 429:
            return {"provider": provider, "error_type": "rate_limited", "message": message or "Rate limited", "retryable": True, "status_code": sc}
        if sc >= 500:
            return {"provider": provider, "error_type": "provider_outage", "message": message or f"Provider outage ({sc}): {text}", "retryable": True, "status_code": sc}
        if sc == 400:
            return {"provider": provider, "error_type": "invalid_request", "message": message or f"Invalid request: {text}", "retryable": False, "status_code": sc}
        return {"provider": provider, "error_type": "unknown", "message": message or f"HTTP {sc}: {text}", "retryable": False, "status_code": sc}
    if exc is not None:
        msg = str(exc)[:300]
        return {"provider": provider, "error_type": "unknown", "message": message or msg, "retryable": False, "status_code": None}
    return {"provider": provider, "error_type": "unknown", "message": message or "Unknown error", "retryable": False, "status_code": None}


def classify_status_code(status_code: int) -> str:
    if status_code == 401:
        return "authentication"
    if status_code == 429:
        return "rate_limited"
    if status_code == 404:
        return "model_not_found"
    if status_code >= 500:
        return "provider_outage"
    if status_code == 400:
        return "invalid_request"
    return "unknown"
