"""Shared input validation.

session_id and restaurant_id were validated by four near-identical copies of the
same regex (routers, models, menu_services, rag_service). restaurant_id becomes a
filesystem path segment, so a copy that drifts is a path traversal; keep one
definition here and import it.

Validators raise ValueError. Routes let it propagate: main.py maps ValueError to
a 400 with the message, and pydantic turns it into a 422 field error.
"""

import re
from typing import Optional

SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
RESTAURANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

SESSION_ID_MAX_LEN = 128
RESTAURANT_ID_MAX_LEN = 64
ITEM_NAME_MAX_LEN = 200
ORDER_REF_MAX_LEN = 64

MIN_QUANTITY = 1
MAX_QUANTITY = 99


def validate_session_id(session_id: Optional[str]) -> str:
    s = (session_id or "").strip()
    if not SESSION_ID_PATTERN.match(s):
        raise ValueError(
            f"session_id must be 1-{SESSION_ID_MAX_LEN} characters: letters, numbers, "
            "underscore, hyphen only"
        )
    return s


def validate_restaurant_id(restaurant_id: Optional[str]) -> str:
    r = (restaurant_id or "").strip()
    if not RESTAURANT_ID_PATTERN.match(r):
        raise ValueError(
            f"restaurant_id must be 1-{RESTAURANT_ID_MAX_LEN} characters: letters, numbers, "
            "underscore, hyphen only"
        )
    return r


def validate_item_name(name: Optional[str]) -> str:
    n = (name or "").strip()
    if not n:
        raise ValueError("item name is required")
    if len(n) > ITEM_NAME_MAX_LEN:
        raise ValueError(f"item name must be at most {ITEM_NAME_MAX_LEN} characters")
    return n


def validate_quantity(quantity) -> int:
    """Coerce and bound a quantity to MIN_QUANTITY..MAX_QUANTITY."""
    if isinstance(quantity, bool):
        raise ValueError("quantity must be a whole number")
    try:
        q = int(quantity)
    except (TypeError, ValueError):
        raise ValueError("quantity must be a whole number")
    if q < MIN_QUANTITY or q > MAX_QUANTITY:
        raise ValueError(f"quantity must be between {MIN_QUANTITY} and {MAX_QUANTITY}")
    return q


def validate_order_reference(order_ref: Optional[str]) -> str:
    """An order number (RESTAURANT_1-0001) or a numeric order id."""
    o = (order_ref or "").strip()
    if not o or len(o) > ORDER_REF_MAX_LEN:
        raise ValueError(f"order reference must be 1-{ORDER_REF_MAX_LEN} characters")
    if not re.match(r"^[A-Za-z0-9_-]+$", o):
        raise ValueError(
            "order reference must be letters, numbers, underscore or hyphen only"
        )
    return o
