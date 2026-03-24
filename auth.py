# API key authentication for protected routes

import os
from typing import Optional

from fastapi import Header, HTTPException

API_KEYS = set(
    k.strip()
    for k in os.getenv("API_KEYS", "").split(",")
    if k.strip()
)
if not API_KEYS and os.getenv("API_KEY"):
    API_KEYS.add(os.getenv("API_KEY", "").strip())


def assert_api_keys_configured() -> None:
    """Call on startup; fail fast if no keys are configured."""
    if not API_KEYS:
        raise RuntimeError(
            "API_KEY or API_KEYS must be set in the environment. "
            "Clients must send the key in the X-API-Key header (or use the React dev proxy)."
        )


def require_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """Require a valid API key on protected routes."""
    if not API_KEYS:
        raise HTTPException(
            status_code=503,
            detail="API key auth not configured (set API_KEY or API_KEYS in env)",
        )
    if not x_api_key or x_api_key.strip() not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key.strip()


def optional_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> Optional[str]:
    """Optional API key; returns the key if present and valid, else None."""
    if not x_api_key:
        return None
    if API_KEYS and x_api_key.strip() in API_KEYS:
        return x_api_key.strip()
    return None
