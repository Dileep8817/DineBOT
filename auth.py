# API key authentication for protected routes

import logging
import os
from typing import Optional

from pathlib import Path

from dotenv import load_dotenv
from fastapi import Header, HTTPException

_PROJECT = Path(__file__).resolve().parent
load_dotenv(_PROJECT / ".env")

logger = logging.getLogger(__name__)

# Matches react-frontend dev proxy default (see .env.development.example)
DEV_DEFAULT_API_KEY = "dinebot-local-dev"

API_KEYS = set(
    k.strip()
    for k in os.getenv("API_KEYS", "").split(",")
    if k.strip()
)
if not API_KEYS and os.getenv("API_KEY"):
    API_KEYS.add(os.getenv("API_KEY", "").strip())

if not API_KEYS:
    logger.warning(
        "No API_KEY in environment; using dev default %r (set API_KEY for production).",
        DEV_DEFAULT_API_KEY,
    )
    API_KEYS.add(DEV_DEFAULT_API_KEY)


def assert_api_keys_configured() -> None:
    """Startup hook; keys are always set (env or dev default)."""
    assert API_KEYS


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
