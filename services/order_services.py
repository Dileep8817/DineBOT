# Cart and order operations (PostgreSQL)

from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from database import get_connection, _next_order_number


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


def create_cart(session_id: str):
    """No-op when using DB; cart exists when it has rows."""
    pass


def add_to_cart(session_id: str, item: dict, quantity: int = 1, *, restaurant_id: str):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO cart_items (session_id, restaurant_id, item_name, price, quantity, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (session_id, restaurant_id, item_name)
                DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity, updated_at = NOW()
                """,
                (session_id, restaurant_id, item["name"], item["price"], quantity),
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


def update_order_status(order_number: str, new_status: str, restaurant_id: str) -> Optional[dict]:
    """Update order status (e.g. pending -> preparing -> ready). Returns updated order or None."""
    allowed = {"pending", "preparing", "ready", "completed", "cancelled"}
    if new_status.lower() not in allowed:
        return None
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE orders SET status = %s
                WHERE order_number = %s AND restaurant_id = %s
                RETURNING id, order_number, status
                """,
                (new_status.lower(), order_number.upper(), restaurant_id),
            )
            row = cur.fetchone()
    if not row:
        return None
    return get_order_for_staff(order_number, restaurant_id)
