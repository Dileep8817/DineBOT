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


def add_to_cart(session_id: str, item: dict, quantity: int = 1, restaurant_id: str = "restaurant_1"):
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


def get_cart(session_id: str, restaurant_id: str = "restaurant_1") -> List[dict]:
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


def clear_cart(session_id: str, restaurant_id: str = "restaurant_1") -> List:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM cart_items WHERE session_id = %s AND restaurant_id = %s",
                (session_id, restaurant_id),
            )
    return []


def get_cart_total(session_id: str, restaurant_id: str = "restaurant_1") -> float:
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


def remove_from_cart(session_id: str, name: str, restaurant_id: str = "restaurant_1") -> List[dict]:
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
    session_id: str, name: str, quantity: int, restaurant_id: str = "restaurant_1"
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


def place_order(session_id: str, restaurant_id: str = "restaurant_1") -> dict:
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


def get_order_status(order_number_or_id: str, restaurant_id: str = "restaurant_1") -> Optional[dict]:
    """Get order by order_number (e.g. RESTAURANT_1-0001) or numeric id."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if order_number_or_id.isdigit():
                cur.execute(
                    """
                    SELECT id, order_number, total, status, created_at
                    FROM orders
                    WHERE id = %s AND restaurant_id = %s
                    """,
                    (int(order_number_or_id), restaurant_id),
                )
            else:
                cur.execute(
                    """
                    SELECT id, order_number, total, status, created_at
                    FROM orders
                    WHERE order_number = %s AND restaurant_id = %s
                    """,
                    (order_number_or_id.upper(), restaurant_id),
                )
            order = _row(cur.fetchone())
            if not order:
                return None
            cur.execute(
                "SELECT item_name, price, quantity FROM order_items WHERE order_id = %s",
                (order["id"],),
            )
            items = cur.fetchall()
    out_items = []
    for r in items:
        d = _row(r)
        out_items.append(
            {"name": d["item_name"], "price": float(d["price"]), "quantity": int(d["quantity"])}
        )
    return {
        "order_number": order["order_number"],
        "total": float(order["total"]),
        "status": order["status"],
        "created_at": str(order["created_at"]),
        "items": out_items,
    }


def update_order_status(order_number: str, new_status: str, restaurant_id: str = "restaurant_1") -> Optional[dict]:
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
    return get_order_status(order_number, restaurant_id)
