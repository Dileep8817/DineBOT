# Cart and order operations (PostgreSQL)

from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from database import get_connection, _next_order_number
from validation import MAX_QUANTITY, validate_item_name, validate_quantity


def _row(row) -> Optional[dict]:
    if row is None:
        return None
    return dict(row)


def _cart_row_to_dict(row) -> dict:
    r = _row(row)
    return {
        "name": r["item_name"],
        "price": float(r["price"]),
        "quantity": int(r["quantity"]),
    }


def add_to_cart(session_id: str, item: dict, quantity: int = 1, *, restaurant_id: str):
    """Add quantity of a menu item, or increase it if the item is already in the cart.

    Bounds are enforced here rather than only in the REST layer because the LLM
    tool path calls straight into this function.
    """
    quantity = validate_quantity(quantity)
    item_name = validate_item_name(item.get("name"))
    price = item.get("price")
    if price is None or float(price) < 0:
        raise ValueError("menu item is missing a valid price")

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO cart_items (session_id, restaurant_id, item_name, price, quantity, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (session_id, restaurant_id, item_name)
                DO UPDATE SET
                    quantity = LEAST(cart_items.quantity + EXCLUDED.quantity, %s),
                    updated_at = NOW()
                """,
                (session_id, restaurant_id, item_name, price, quantity, MAX_QUANTITY),
            )
    return get_cart(session_id, restaurant_id)


def get_cart(session_id: str, restaurant_id: str) -> List[dict]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT item_name, price, quantity
                FROM cart_items
                WHERE session_id = %s AND restaurant_id = %s
                ORDER BY item_name
                """,
                (session_id, restaurant_id),
            )
            rows = cur.fetchall()
    return [_cart_row_to_dict(r) for r in rows]


def clear_cart(session_id: str, restaurant_id: str) -> List:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM cart_items WHERE session_id = %s AND restaurant_id = %s",
                (session_id, restaurant_id),
            )
    return []


def get_cart_total(session_id: str, restaurant_id: str) -> float:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(price * quantity), 0) AS total
                FROM cart_items
                WHERE session_id = %s AND restaurant_id = %s
                """,
                (session_id, restaurant_id),
            )
            row = cur.fetchone()
    return float(row[0])


def remove_from_cart(session_id: str, name: str, restaurant_id: str) -> List[dict]:
    name = validate_item_name(name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM cart_items
                WHERE session_id = %s AND restaurant_id = %s AND LOWER(item_name) = LOWER(%s)
                """,
                (session_id, restaurant_id, name),
            )
    return get_cart(session_id, restaurant_id)


def update_cart_item(
    session_id: str, name: str, quantity: int, restaurant_id: str
) -> List[dict]:
    """Set an item's quantity. To remove an item use remove_from_cart; 0 is not a valid quantity."""
    name = validate_item_name(name)
    quantity = validate_quantity(quantity)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE cart_items
                SET quantity = %s, updated_at = NOW()
                WHERE session_id = %s AND restaurant_id = %s AND LOWER(item_name) = LOWER(%s)
                """,
                (quantity, session_id, restaurant_id, name),
            )
    return get_cart(session_id, restaurant_id)


def place_order(session_id: str, restaurant_id: str) -> dict:
    """Create order from current cart, clear cart, return order_id and total."""
    cart = get_cart(session_id, restaurant_id)
    if not cart:
        return {"error": "Cart is empty"}
    total = get_cart_total(session_id, restaurant_id)
    last_exc = None
    for _ in range(10):
        order_number = None
        try:
            with get_connection() as conn:
                order_number = _next_order_number(conn, restaurant_id)
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        INSERT INTO orders (order_number, session_id, restaurant_id, total, status)
                        VALUES (%s, %s, %s, %s, 'pending')
                        RETURNING id, order_number, total, status, created_at
                        """,
                        (order_number, session_id, restaurant_id, total),
                    )
                    order = _row(cur.fetchone())
                    order_id = order["id"]
                    for item in cart:
                        cur.execute(
                            """
                            INSERT INTO order_items (order_id, item_name, price, quantity)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (order_id, item["name"], item["price"], item["quantity"]),
                        )
                    cur.execute(
                        "DELETE FROM cart_items WHERE session_id = %s AND restaurant_id = %s",
                        (session_id, restaurant_id),
                    )
            return {
                "order_id": order_id,
                "order_number": order_number,
                "total": float(total),
                "status": order["status"],
            }
        except psycopg2.errors.UniqueViolation as e:
            last_exc = e
            continue
    raise last_exc


ORDER_COLUMNS = """
    id, order_number, total, status,
    COALESCE(payment_status, 'unpaid') AS payment_status,
    created_at
"""


def _fetch_order(
    order_number_or_id: str, restaurant_id: str, session_id: Optional[str]
) -> Optional[dict]:
    """Read one order plus its items.

    When session_id is given, the order must belong to that session; that is the
    only lookup a customer-facing caller may use. Pass None only from a path that
    has already checked staff authorization.
    """
    by_id = order_number_or_id.isdigit()
    key = int(order_number_or_id) if by_id else order_number_or_id.upper()
    where = "id = %s" if by_id else "order_number = %s"
    params = [key, restaurant_id]
    if session_id is not None:
        where += " AND session_id = %s"
        params.append(session_id)

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"SELECT {ORDER_COLUMNS} FROM orders WHERE {where} AND restaurant_id = %s",
                tuple(params),
            )
            order = _row(cur.fetchone())
            if not order:
                return None
            cur.execute(
                "SELECT item_name, price, quantity FROM order_items WHERE order_id = %s",
                (order["id"],),
            )
            items = cur.fetchall()

    out_items = [
        {
            "name": d["item_name"],
            "price": float(d["price"]),
            "quantity": int(d["quantity"]),
        }
        for d in (_row(r) for r in items)
    ]
    return {
        "order_number": order["order_number"],
        "total": float(order["total"]),
        "status": order["status"],
        "payment_status": order["payment_status"],
        "created_at": str(order["created_at"]),
        "items": out_items,
    }


def get_order_status(
    order_number_or_id: str, restaurant_id: str, *, session_id: str
) -> Optional[dict]:
    """Customer-facing order lookup, scoped to the session that placed the order.

    Order numbers are sequential per restaurant, so scoping by restaurant_id
    alone let anyone enumerate every order in the venue. session_id is required
    and keyword-only so a caller cannot omit it or pass it by accident.
    """
    if not session_id:
        raise ValueError("session_id is required to read an order")
    return _fetch_order(order_number_or_id, restaurant_id, session_id)


def get_order_for_staff(order_number_or_id: str, restaurant_id: str) -> Optional[dict]:
    """Read any order for a restaurant, ignoring which session placed it.

    Callers MUST be behind staff authorization (see auth.require_staff_key).
    """
    return _fetch_order(order_number_or_id, restaurant_id, None)


def list_orders_for_staff(
    restaurant_id: str,
    statuses: Optional[List[str]] = None,
    updated_after: Optional[str] = None,
    limit: int = 100,
) -> List[dict]:
    """Orders for a restaurant, newest change first, with their line items.

    Callers MUST be behind staff authorization (see auth.require_staff_key).
    updated_after is an ISO timestamp used by the live stream to fetch only what
    changed since the last poll.
    """
    limit = max(1, min(int(limit), 500))
    clauses = ["restaurant_id = %s"]
    params: list = [restaurant_id]
    if statuses:
        clauses.append("status = ANY(%s)")
        params.append([s.strip().lower() for s in statuses])
    if updated_after:
        clauses.append("updated_at > %s")
        params.append(updated_after)
    params.append(limit)

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT id, order_number, session_id, total, status,
                       COALESCE(payment_status, 'unpaid') AS payment_status,
                       created_at, updated_at
                FROM orders
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at ASC
                LIMIT %s
                """,
                tuple(params),
            )
            orders = [_row(r) for r in cur.fetchall()]
            if not orders:
                return []
            cur.execute(
                """
                SELECT order_id, item_name, price, quantity
                FROM order_items
                WHERE order_id = ANY(%s)
                ORDER BY id
                """,
                ([o["id"] for o in orders],),
            )
            items_by_order = {}
            for raw in cur.fetchall():
                item = _row(raw)
                items_by_order.setdefault(item["order_id"], []).append(
                    {
                        "name": item["item_name"],
                        "price": float(item["price"]),
                        "quantity": int(item["quantity"]),
                    }
                )

    return [
        {
            "order_id": o["id"],
            "order_number": o["order_number"],
            "status": o["status"],
            "payment_status": o["payment_status"],
            "total": float(o["total"]),
            "created_at": str(o["created_at"]),
            "updated_at": str(o["updated_at"]),
            "items": items_by_order.get(o["id"], []),
        }
        for o in orders
    ]


ORDER_STATUSES = ("pending", "preparing", "ready", "completed", "cancelled")

# The kitchen flow, plus cancelling anything not already finished. Nothing leaves
# a terminal state: a completed order that can go back to pending would let a
# paid order be re-run, and re-opening a cancelled order hides that it happened.
STATUS_TRANSITIONS = {
    "pending": ("preparing", "cancelled"),
    "preparing": ("ready", "cancelled"),
    "ready": ("completed",),
    "completed": (),
    "cancelled": (),
}


class InvalidStatusTransition(ValueError):
    """Raised when a status change is not allowed from the order's current status."""

    def __init__(self, current: str, requested: str):
        self.current = current
        self.requested = requested
        self.allowed = list(STATUS_TRANSITIONS.get(current, ()))
        allowed = ", ".join(self.allowed) if self.allowed else "nothing (final status)"
        super().__init__(
            f"cannot move an order from {current!r} to {requested!r}; allowed from "
            f"{current!r}: {allowed}"
        )


def next_status(current: str) -> Optional[str]:
    """The forward step in the kitchen flow, or None at the end of it."""
    forward = [s for s in STATUS_TRANSITIONS.get(current, ()) if s != "cancelled"]
    return forward[0] if forward else None


def update_order_status(order_number: str, new_status: str, restaurant_id: str) -> Optional[dict]:
    """Advance an order along the status flow. Returns the order, or None if absent.

    Raises ValueError for an unknown status and InvalidStatusTransition for a move
    the flow does not allow. Callers MUST be staff-authorized.
    """
    requested = (new_status or "").strip().lower()
    if requested not in ORDER_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(ORDER_STATUSES)}")

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Lock the row so two staff tapping at once cannot both pass the check.
            cur.execute(
                """
                SELECT id, status FROM orders
                WHERE order_number = %s AND restaurant_id = %s
                FOR UPDATE
                """,
                (order_number.upper(), restaurant_id),
            )
            row = _row(cur.fetchone())
            if not row:
                return None
            current = row["status"]
            if requested == current:
                return get_order_for_staff(order_number, restaurant_id)
            if requested not in STATUS_TRANSITIONS.get(current, ()):
                raise InvalidStatusTransition(current, requested)
            cur.execute(
                """
                UPDATE orders SET status = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (requested, row["id"]),
            )
    return get_order_for_staff(order_number, restaurant_id)
