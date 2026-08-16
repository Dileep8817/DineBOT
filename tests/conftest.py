"""Shared test setup.

The suite runs against a real PostgreSQL, because most of the behaviour worth
testing here is SQL: the cart upsert, the order status transition under a row
lock, and the session scoping that closed the IDOR. A test database is derived
from DATABASE_URL (or set TEST_DATABASE_URL) and created if missing, so tests
never touch the development database. Without a reachable server the whole suite
skips rather than failing.

Environment is set before importing any application module, since config.py reads
DATA_DIR and database.py reads DATABASE_URL at import time.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# config.py normally does this, but it must not be imported until the test
# environment below is in place.
load_dotenv(PROJECT_ROOT / ".env")

CUSTOMER_KEY = "test-customer-key"
STAFF_KEY = "test-staff-key"
RESTAURANT_ID = "restaurant_1"


def _test_database_url():
    explicit = (os.getenv("TEST_DATABASE_URL") or "").strip()
    if explicit:
        return explicit
    base = (os.getenv("DATABASE_URL") or "").strip()
    if not base:
        return None
    parts = urlparse(base)
    name = (parts.path or "/dinebot").lstrip("/") or "dinebot"
    if name.endswith("_test"):
        return base
    return urlunparse(parts._replace(path=f"/{name}_test"))


def _ensure_database(url) -> str:
    """Create the test database if it does not exist. Returns a skip reason or ""."""
    import psycopg2
    from psycopg2 import sql

    parts = urlparse(url)
    name = parts.path.lstrip("/")
    admin_url = urlunparse(parts._replace(path="/postgres"))
    try:
        conn = psycopg2.connect(admin_url, connect_timeout=5)
    except Exception as e:
        return f"PostgreSQL is not reachable ({e.__class__.__name__}): {e}"
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    except Exception as e:
        return f"Could not create the test database {name!r}: {e}"
    finally:
        conn.close()
    return ""


_TEST_DB_URL = _test_database_url()
_SKIP_REASON = (
    "No DATABASE_URL or TEST_DATABASE_URL configured"
    if not _TEST_DB_URL
    else _ensure_database(_TEST_DB_URL)
)

if not _SKIP_REASON:
    os.environ["DATABASE_URL"] = _TEST_DB_URL
    os.environ["DATA_DIR"] = str(PROJECT_ROOT / "sample_data")
    os.environ["API_KEY"] = CUSTOMER_KEY
    os.environ["STAFF_API_KEY"] = STAFF_KEY
    os.environ.pop("API_KEYS", None)
    os.environ.pop("STAFF_API_KEYS", None)
    os.environ.pop("DINEBOT_DEV", None)
    # Keep the suite offline and deterministic.
    os.environ["RAG_INDEX_ON_STARTUP"] = "0"
    os.environ["SEED_SAMPLE_DATA"] = "0"
    os.environ.pop("OPENAI_API_KEY", None)


def pytest_collection_modifyitems(config, items):
    if not _SKIP_REASON:
        return
    skip = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        item.add_marker(skip)


@pytest.fixture(scope="session")
def app_module():
    from database import init_db

    init_db()
    import main

    # Rate limits would make repeated calls in a module flaky.
    main.app.state.limiter.enabled = False
    return main


@pytest.fixture()
def client(app_module):
    from fastapi.testclient import TestClient

    return TestClient(app_module.app)


@pytest.fixture(autouse=True)
def clean_tables(app_module):
    """Every test starts with empty carts, orders and chat history."""
    from database import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE order_items, orders, cart_items, chat_history RESTART IDENTITY CASCADE"
            )
    yield


@pytest.fixture()
def customer_headers():
    return {"X-API-Key": CUSTOMER_KEY}


@pytest.fixture()
def staff_headers():
    return {"X-Staff-Key": STAFF_KEY}


@pytest.fixture()
def restaurant_id():
    return RESTAURANT_ID


@pytest.fixture()
def place_order_for():
    """Put one item in a session's cart and check out. Returns the order dict."""
    from services.menu_services import get_menu_item
    from services.order_services import add_to_cart, place_order

    def _place(session_id, item_name="Cheese Pizza", quantity=1, restaurant_id=RESTAURANT_ID):
        item = get_menu_item(restaurant_id, item_name)
        add_to_cart(session_id, item, quantity=quantity, restaurant_id=restaurant_id)
        return place_order(session_id, restaurant_id)

    return _place
