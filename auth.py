# Optional API key auth for admin / protected endpoints

import os
from typing import Optional
from fastapi import Header, HTTPException

API_KEYS = set(
    k.strip()
    for k in os.getenv("API_KEYS", "").split(",")
    if k.strip()
)
# Single key for convenience
if not API_KEYS and os.getenv("API_KEY"):
    API_KEYS.add(os.getenv("API_KEY", "").strip())


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Require a valid API key. Use for admin/protected routes."""
    if not API_KEYS:
        raise HTTPException(
            status_code=503,
            detail="API key auth not configured (set API_KEY or API_KEYS in env)",
        )
    if x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key


def optional_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> Optional[str]:
    """Optional API key; returns the key if present and valid, else None."""
    if not x_api_key:
        return None
    if API_KEYS and x_api_key in API_KEYS:
        return x_api_key
    return None
