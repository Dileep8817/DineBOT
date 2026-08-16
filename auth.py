# API key authentication for protected routes

import logging
import os
import secrets
from typing import Optional, Set

from fastapi import Header, HTTPException

from config import PROJECT_ROOT  # noqa: F401  importing config loads the project .env

logger = logging.getLogger(__name__)

# Publicly known keys, committed to this repo and to .env.example. They are only
# usable when DINEBOT_DEV=1 is set explicitly, so they can never be the reason a
# production deployment ends up unauthenticated.
DEV_DEFAULT_API_KEY = "dinebot-local-dev"
DEV_DEFAULT_STAFF_KEY = "dinebot-local-staff"

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


# --- Staff authorization -----------------------------------------------------
# Deliberately a different secret in a different header from the customer key.
# The customer key is handed to every browser session that loads the widget, so
# it cannot also be what authorizes reading the whole restaurant's orders.


def get_staff_keys() -> Set[str]:
    """Accepted staff keys, from STAFF_API_KEYS (csv) and STAFF_API_KEY.

    Empty means the staff endpoints are not enabled on this deployment.
    """
    keys = {k.strip() for k in (os.getenv("STAFF_API_KEYS") or "").split(",") if k.strip()}
    single = (os.getenv("STAFF_API_KEY") or "").strip()
    if single:
        keys.add(single)

    if keys:
        if DEV_DEFAULT_STAFF_KEY in keys and not dev_mode():
            raise RuntimeError(
                f"STAFF_API_KEY/STAFF_API_KEYS contains the public development key "
                f"{DEV_DEFAULT_STAFF_KEY!r}, which is committed to this repository. "
                f"Set a generated key, or set DINEBOT_DEV=1 for local development."
            )
        overlap = keys & _configured_api_keys()
        if overlap:
            raise RuntimeError(
                "A staff key must not also be a customer API key: the customer key is "
                "served to every browser that loads the ordering widget, so sharing it "
                "would give customers staff access. Use separate values."
            )
        return keys

    if dev_mode():
        logger.warning(
            "DINEBOT_DEV=1 and no STAFF_API_KEY set: accepting the public staff key %r.",
            DEV_DEFAULT_STAFF_KEY,
        )
        return {DEV_DEFAULT_STAFF_KEY}
    return set()


def assert_staff_keys_valid() -> None:
    """Startup check: surface a bad staff key configuration immediately.

    Absent keys are allowed (the staff endpoints simply answer 503); a key that
    collides with a customer key is a misconfiguration and stops startup.
    """
    get_staff_keys()


def require_staff_key(x_staff_key: Optional[str] = Header(None, alias="X-Staff-Key")) -> str:
    """Require a valid staff key. Used only by the /staff routes."""
    keys = get_staff_keys()
    if not keys:
        raise HTTPException(
            status_code=503,
            detail="Staff access is not configured on this server (set STAFF_API_KEY)",
        )
    candidate = (x_staff_key or "").strip()
    if not candidate or not _matches(candidate, keys):
        raise HTTPException(status_code=401, detail="Invalid or missing staff key")
    return candidate
