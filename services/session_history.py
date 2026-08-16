"""Conversation history for the chat endpoint, stored in PostgreSQL.

This replaces a module-level dict. That dict was unbounded (one entry per
session id ever seen, never evicted, so a long-running process grew forever) and
per-process, so with more than one uvicorn worker a customer's next message
could land on a worker that had never seen the conversation.

History is capped per conversation and expires, and a failure to read or write it
degrades to a stateless turn rather than failing the request: losing context is
better than losing the reply.
"""

import json
import logging
import os
import time
from typing import List

from psycopg2.extras import Json

from database import get_connection

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int((os.getenv(name) or "").strip() or default)
    except ValueError:
        logger.warning("%s is not an integer, using %d", name, default)
        return default
    return max(minimum, value)


# Messages kept per conversation. Each turn appends the user message plus any
# assistant/tool messages, so this is a few turns, not a few dozen.
MAX_HISTORY_MESSAGES = _int_env("CHAT_HISTORY_MAX_MESSAGES", 20, minimum=2)
# A conversation idle this long starts fresh.
HISTORY_TTL_MINUTES = _int_env("CHAT_HISTORY_TTL_MINUTES", 120)
# Guard against a single message growing the row without bound.
MAX_MESSAGE_CHARS = _int_env("CHAT_HISTORY_MAX_MESSAGE_CHARS", 4000, minimum=200)

_PRUNE_INTERVAL_SECONDS = 300
_last_prune = 0.0


def _truncate(messages: List[dict]) -> List[dict]:
    """Keep the most recent messages and cap the size of each one."""
    trimmed = []
    for msg in messages[-MAX_HISTORY_MESSAGES:]:
        content = msg.get("content")
        if isinstance(content, str) and len(content) > MAX_MESSAGE_CHARS:
            msg = dict(msg)
            msg["content"] = content[:MAX_MESSAGE_CHARS] + "… (truncated)"
        trimmed.append(msg)
    return trimmed


def get_history(session_id: str, restaurant_id: str) -> List[dict]:
    """Messages for this conversation, or [] if absent, expired or unreadable."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT messages
                    FROM chat_history
                    WHERE session_id = %s
                      AND restaurant_id = %s
                      AND updated_at > NOW() - (%s * INTERVAL '1 minute')
                    """,
                    (session_id, restaurant_id, HISTORY_TTL_MINUTES),
                )
                row = cur.fetchone()
    except Exception as e:
        logger.warning("Could not read chat history for %s: %s", session_id, e)
        return []
    if not row or not row[0]:
        return []
    messages = row[0]
    if isinstance(messages, str):  # older rows, or a driver without JSONB decoding
        try:
            messages = json.loads(messages)
        except ValueError:
            return []
    return messages if isinstance(messages, list) else []


def save_history(session_id: str, restaurant_id: str, messages: List[dict]) -> None:
    """Replace the stored history, trimmed to the configured bounds."""
    trimmed = _truncate(messages)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_history (session_id, restaurant_id, messages, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (session_id, restaurant_id)
                    DO UPDATE SET messages = EXCLUDED.messages, updated_at = NOW()
                    """,
                    (session_id, restaurant_id, Json(trimmed)),
                )
    except Exception as e:
        logger.warning("Could not save chat history for %s: %s", session_id, e)
        return
    _prune_if_due()


def clear_history(session_id: str, restaurant_id: str) -> None:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM chat_history WHERE session_id = %s AND restaurant_id = %s",
                    (session_id, restaurant_id),
                )
    except Exception as e:
        logger.warning("Could not clear chat history for %s: %s", session_id, e)


def prune_expired() -> int:
    """Delete conversations idle for longer than the TTL. Returns rows removed."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM chat_history "
                    "WHERE updated_at < NOW() - (%s * INTERVAL '1 minute')",
                    (HISTORY_TTL_MINUTES,),
                )
                return cur.rowcount or 0
    except Exception as e:
        logger.warning("Could not prune chat history: %s", e)
        return 0


def _prune_if_due() -> None:
    """Prune at most every _PRUNE_INTERVAL_SECONDS, so writes stay cheap."""
    global _last_prune
    now = time.monotonic()
    if now - _last_prune < _PRUNE_INTERVAL_SECONDS:
        return
    _last_prune = now
    removed = prune_expired()
    if removed:
        logger.info("Pruned %d expired chat conversation(s)", removed)
