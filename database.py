# Database connection and schema for carts and orders (PostgreSQL or SQLite)

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "dinebot.db"


def _parse_database_config():
    """Use SQLite unless DATABASE_URL is a working PostgreSQL URL."""
    import logging

    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return "sqlite", str(DEFAULT_SQLITE_PATH)
    if url.startswith("sqlite:"):
        if url.startswith("sqlite:///"):
            rest = url[10:]
            path = rest if os.path.isabs(rest) else str(PROJECT_ROOT / rest)
        else:
            path = str(DEFAULT_SQLITE_PATH)
        return "sqlite", path
    if os.getenv("DATABASE_FORCE_POSTGRES", "").strip().lower() in ("1", "true", "yes"):
        return "postgres", url
    try:
        import psycopg2

        conn = psycopg2.connect(url, connect_timeout=5)
        conn.close()
        return "postgres", url
    except Exception as e:
        logging.getLogger(__name__).warning(
            "PostgreSQL unavailable (%s); using SQLite at %s. "
            "Fix DATABASE_URL or set DATABASE_FORCE_POSTGRES=1 to fail fast.",
            e,
            DEFAULT_SQLITE_PATH,
        )
        return "sqlite", str(DEFAULT_SQLITE_PATH)


DB_KIND, _DB_DSN = _parse_database_config()
IS_SQLITE = DB_KIND == "sqlite"
SQLITE_PATH = _DB_DSN if IS_SQLITE else None
DATABASE_URL = _DB_DSN  # for health/debug: path or postgres URL


def adapt_sql(sql: str) -> str:
    """Normalize SQL for SQLite: placeholders, timestamps, UPSERT excluded row."""
    if not IS_SQLITE:
        return sql
    s = sql.replace("%s", "?").replace("NOW()", "CURRENT_TIMESTAMP")
    return s.replace("EXCLUDED.", "excluded.")


def dict_cursor(conn):
    """Row as dict for both backends."""
    if IS_SQLITE:
        return conn.cursor()
    from psycopg2.extras import RealDictCursor

    return conn.cursor(cursor_factory=RealDictCursor)


@contextmanager
def get_connection():
    if IS_SQLITE:
        conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        import psycopg2

        conn = psycopg2.connect(_DB_DSN)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist. Run once on startup or via script."""
    with get_connection() as conn:
        cur = conn.cursor()
        if IS_SQLITE:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cart_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(255) NOT NULL,
                    restaurant_id VARCHAR(64) NOT NULL,
                    item_name VARCHAR(255) NOT NULL,
                    price REAL NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
                    updated_at TEXT DEFAULT (CURRENT_TIMESTAMP),
                    UNIQUE(session_id, restaurant_id, item_name)
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number VARCHAR(32) UNIQUE NOT NULL,
                    session_id VARCHAR(255) NOT NULL,
                    restaurant_id VARCHAR(64) NOT NULL,
                    total REAL NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    created_at TEXT DEFAULT (CURRENT_TIMESTAMP)
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    item_name VARCHAR(255) NOT NULL,
                    price REAL NOT NULL,
                    quantity INTEGER NOT NULL
                );
                """
            )
        else:
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
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
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
    """Generate daily order number. For high concurrency, consider a SEQUENCE or SELECT FOR UPDATE."""
    cur = conn.cursor()
    if IS_SQLITE:
        cur.execute(
            """
            SELECT COUNT(*) + 1 FROM orders
            WHERE restaurant_id = ? AND date(created_at) = date('now')
            """,
            (restaurant_id,),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*) + 1 FROM orders
            WHERE restaurant_id = %s AND created_at >= CURRENT_DATE
            """,
            (restaurant_id,),
        )
    n = cur.fetchone()[0]
    return f"{restaurant_id.upper()}-{n:04d}"


def row_to_dict(row):
    """sqlite3.Row or dict-like -> dict"""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)
