# main file for creating/running the server

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import limiter  # loads PROJECT_ROOT/.env before other app modules read env
from auth import assert_api_keys_configured, dev_mode
from database import init_db
from routers.menu_routes import router as menu_router
from services.menu_services import AmbiguousMenuItem, RestaurantDataNotFound
from routers.order_routes import router as order_router
from routers.chat_routes import router as chat_router
from routers.payment_routes import payment_router, webhook_router

_log_level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level_name, logging.INFO),
    format="%(asctime)s %(levelname)s: %(name)s: %(message)s",
)


def _seed_sample_data_if_requested():
    """Copy sample_data/ into DATA_DIR when SEED_SAMPLE_DATA is truthy.

    Off by default so a real deployment never has demo restaurants appear; the
    Docker image turns it on so `docker compose up` has a menu to serve.
    """
    if (os.getenv("SEED_SAMPLE_DATA") or "").strip().lower() not in ("1", "true", "yes"):
        return
    from scripts.seed_data import seed_sample_data

    seeded = seed_sample_data()
    if seeded:
        logging.getLogger(__name__).info("Seeded sample restaurants: %s", ", ".join(seeded))


def on_startup():
    assert_api_keys_configured()
    _seed_sample_data_if_requested()
    init_db()
    try:
        from services.rag_service import index_all_restaurants

        n = index_all_restaurants()
        if n > 0:
            logging.getLogger(__name__).info("RAG indexed %d chunks on startup", n)
    except Exception as e:
        logging.getLogger(__name__).warning("RAG indexing skipped or failed: %s", e)


DEV_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def allowed_origins():
    """Browser origins permitted to call the API directly, from ALLOWED_ORIGINS.

    Empty means no CORS middleware is installed, which is the right answer when
    the SPA is served from the same hostname as the API (the documented setup).
    """
    origins = [o.strip() for o in (os.getenv("ALLOWED_ORIGINS") or "").split(",") if o.strip()]
    if "*" in origins:
        if not dev_mode():
            raise RuntimeError(
                "ALLOWED_ORIGINS=* would let any site call this API with a browser's "
                "credentials. List the exact origins, or set DINEBOT_DEV=1 locally."
            )
        return ["*"]
    if origins:
        return origins
    if dev_mode():
        return list(DEV_ORIGINS)
    return []


app = FastAPI(title="Restaurant AI Agent")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_origins = allowed_origins()
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "X-Staff-Key"],
    )
    logging.getLogger(__name__).info("CORS enabled for: %s", ", ".join(_origins))


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(AmbiguousMenuItem)
async def ambiguous_menu_item_handler(request, exc: AmbiguousMenuItem):
    """409 rather than picking one of the candidates for the customer."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=409,
        content={
            "detail": str(exc),
            "query": exc.query,
            "matches": exc.matches,
        },
    )


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
