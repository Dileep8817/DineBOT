# PostgreSQL connection and schema for carts and orders

import os
from contextlib import contextmanager

import psycopg2

from config import PROJECT_ROOT  # noqa: F401  importing config loads the project .env

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required (PostgreSQL only). "
        "Example: postgresql://user:password@localhost:5432/restaurant_ai"
    )


@contextmanager
def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cart_items (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    restaurant_id VARCHAR(64) NOT NULL,
                    item_name VARCHAR(255) NOT NULL,
                    price NUMERIC(10, 2) NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(session_id, restaurant_id, item_name)
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    order_number VARCHAR(32) UNIQUE NOT NULL,
                    session_id VARCHAR(255) NOT NULL,
                    restaurant_id VARCHAR(64) NOT NULL,
                    total NUMERIC(10, 2) NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    payment_status VARCHAR(32) NOT NULL DEFAULT 'unpaid',
                    stripe_payment_intent_id VARCHAR(255),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            # Migrations for databases created before these columns existed.
            cur.execute(
                """
                ALTER TABLE orders
                    ADD COLUMN IF NOT EXISTS payment_status VARCHAR(32) NOT NULL DEFAULT 'unpaid',
                    ADD COLUMN IF NOT EXISTS stripe_payment_intent_id VARCHAR(255),
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
                """
            )
            # An earlier version of this migration stored the default as the literal
            # text "'unpaid'" (quotes included), so rows created by it never compare
            # equal to 'unpaid'. ADD COLUMN IF NOT EXISTS cannot fix an existing
            # column, so normalise the default and repair those rows.
            cur.execute("ALTER TABLE orders ALTER COLUMN payment_status SET DEFAULT 'unpaid';")
            cur.execute(
                "UPDATE orders SET payment_status = btrim(payment_status, '''') "
                "WHERE payment_status LIKE '''%';"
            )
            # The staff order stream polls by (restaurant_id, updated_at).
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_orders_restaurant_updated "
                "ON orders (restaurant_id, updated_at);"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    session_id VARCHAR(128) NOT NULL,
                    restaurant_id VARCHAR(64) NOT NULL,
                    messages JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (session_id, restaurant_id)
                );
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_history_updated_at "
                "ON chat_history (updated_at);"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS order_items (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    item_name VARCHAR(255) NOT NULL,
                    price NUMERIC(10, 2) NOT NULL,
                    quantity INTEGER NOT NULL
                );
                """
            )


def _next_order_number(conn, restaurant_id: str):
    """
    Next display id for this restaurant. Uses max numeric suffix across ALL orders
    for this restaurant (not only today) so order_number stays unique globally.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(
                MAX(CAST(SUBSTRING(order_number FROM '[0-9]+$') AS INTEGER)),
                0
            ) + 1
            FROM orders
            WHERE restaurant_id = %s
            """,
            (restaurant_id,),
        )
        n = cur.fetchone()[0]
    return f"{restaurant_id.upper()}-{n:04d}"
