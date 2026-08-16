# API key authentication for protected routes

import logging
import os
import secrets
from typing import Optional, Set

from fastapi import Header, HTTPException

from config import PROJECT_ROOT  # noqa: F401  importing config loads the project .env

logger = logging.getLogger(__name__)

# Publicly known key, committed to this repo and to .env.example. It is only
# usable when DINEBOT_DEV=1 is set explicitly, so it can never be the reason a
# production deployment ends up unauthenticated.
DEV_DEFAULT_API_KEY = "dinebot-local-dev"

_TRUTHY = ("1", "true", "yes", "on")


def _env_flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in _TRUTHY


def dev_mode() -> bool:
    """True when the operator opted into local dev conveniences (DINEBOT_DEV=1)."""
    return _env_flag("DINEBOT_DEV")


def _configured_api_keys() -> Set[str]:
    """Keys explicitly set in the environment, from API_KEYS (csv) and API_KEY."""
    keys = {k.strip() for k in (os.getenv("API_KEYS") or "").split(",") if k.strip()}
    single = (os.getenv("API_KEY") or "").strip()
    if single:
        keys.add(single)
    return keys


def get_api_keys() -> Set[str]:
    """Accepted customer API keys. Empty means auth is not configured.

    Read from the environment on each call so tests and reloads see changes.
    """
    keys = _configured_api_keys()
    if keys:
        if DEV_DEFAULT_API_KEY in keys and not dev_mode():
            raise RuntimeError(
                f"API_KEY/API_KEYS contains the public development key "
                f"{DEV_DEFAULT_API_KEY!r}. It is committed to this repository, so it "
                f"authenticates nobody. Set a generated key, or set DINEBOT_DEV=1 if "
                f"this really is a local machine."
            )
        return keys
    if dev_mode():
        logger.warning(
            "DINEBOT_DEV=1 and no API_KEY set: accepting the public development key %r. "
            "Never do this outside a local machine.",
            DEV_DEFAULT_API_KEY,
        )
        return {DEV_DEFAULT_API_KEY}
    return set()


def assert_api_keys_configured() -> None:
    """Startup gate: refuse to serve traffic with no usable API key."""
    if get_api_keys():
        return
    raise RuntimeError(
        "No API key configured. Set API_KEY (or a comma-separated API_KEYS) in the "
        "environment. For local development only, set DINEBOT_DEV=1 to accept the "
        f"public key {DEV_DEFAULT_API_KEY!r}."
    )


def _matches(candidate: str, keys: Set[str]) -> bool:
    """Compare against every key in constant time to avoid leaking a prefix."""
    return any(secrets.compare_digest(candidate, k) for k in keys)


def require_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """Require a valid customer API key on protected routes."""
    keys = get_api_keys()
    if not keys:
        raise HTTPException(
            status_code=503,
            detail="API key auth is not configured on this server",
        )
    candidate = (x_api_key or "").strip()
    if not candidate or not _matches(candidate, keys):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return candidate


def optional_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> Optional[str]:
    """Optional API key; returns the key if present and valid, else None."""
    if not x_api_key:
        return None
    keys = get_api_keys()
    if keys and _matches(x_api_key.strip(), keys):
        return x_api_key.strip()
    return None
