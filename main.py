# main file for creating/running the server

import logging
import os

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import limiter  # loads PROJECT_ROOT/.env before other app modules read env
from auth import assert_api_keys_configured
from database import init_db
from routers.menu_routes import router as menu_router
from services.menu_services import RestaurantDataNotFound
from routers.order_routes import router as order_router
from routers.chat_routes import router as chat_router
from routers.payment_routes import payment_router, webhook_router

_log_level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level_name, logging.INFO),
    format="%(asctime)s %(levelname)s: %(name)s: %(message)s",
)


def on_startup():
    assert_api_keys_configured()
    init_db()
    try:
        from services.rag_service import index_all_restaurants

        n = index_all_restaurants()
        if n > 0:
            logging.getLogger(__name__).info("RAG indexed %d chunks on startup", n)
    except Exception as e:
        logging.getLogger(__name__).warning("RAG indexing skipped or failed: %s", e)


app = FastAPI(title="Restaurant AI Agent")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RestaurantDataNotFound)
async def restaurant_data_not_found_handler(request, exc: RestaurantDataNotFound):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=404,
        content={
            "detail": f"No menu data for restaurant_id={exc.restaurant_id!r} (missing {exc.filename}). "
            f"Use a folder under DATA_DIR with that name, e.g. data/velvet_fork_kitchen/menu.json."
        },
    )


app.add_event_handler("startup", on_startup)

app.include_router(menu_router)
app.include_router(order_router)
app.include_router(chat_router)
app.include_router(payment_router)
app.include_router(webhook_router)


@app.get("/")
async def root():
    return {"message": "Restaurant AI Agent API is running"}


@app.get("/health")
async def health():
    """Health check for monitoring / load balancers."""
    try:
        from database import get_connection

        with get_connection():
            pass
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"status": "error", "database": str(e)})
