# Order and cart API with validation, API key, and rate limiting

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_api_key
from config import limiter
from services.menu_services import get_menu_item
from services.order_services import (
    add_to_cart,
    get_cart,
    clear_cart,
    remove_from_cart,
    update_cart_item,
    place_order,
    get_order_status,
    update_order_status,
)

router = APIRouter(dependencies=[Depends(require_api_key)])

SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
ITEM_NAME_MAX_LEN = 200


def _validate_session_id(session_id: str) -> None:
    if not SESSION_ID_PATTERN.match(session_id):
        raise HTTPException(
            status_code=400,
            detail="session_id: 1-128 chars, alphanumeric, underscore, hyphen only",
        )


def _validate_item_name(name: str) -> str:
    n = (name or "").strip()
    if not n or len(n) > ITEM_NAME_MAX_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"name must be 1-{ITEM_NAME_MAX_LEN} characters",
        )
    return n


@router.post("/cart/add")
@limiter.limit("90/minute")
async def add_item(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=128),
    name: str = Query(..., min_length=1, max_length=ITEM_NAME_MAX_LEN),
):
    _validate_session_id(session_id)
    name = _validate_item_name(name)
    item = get_menu_item("restaurant_1", name)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    add_to_cart(session_id, item)
    return {"message": f"{name} added to cart"}


@router.get("/cart")
@limiter.limit("120/minute")
async def cart(request: Request, session_id: str = Query(..., min_length=1, max_length=128)):
    _validate_session_id(session_id)
    return get_cart(session_id)


@router.post("/cart/clear")
@limiter.limit("60/minute")
async def clear(request: Request, session_id: str = Query(..., min_length=1, max_length=128)):
    _validate_session_id(session_id)
    return clear_cart(session_id)


@router.get("/cart/summary")
@limiter.limit("120/minute")
async def cart_summary(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=128),
):
    _validate_session_id(session_id)
    cart = get_cart(session_id)
    total = sum(item["price"] * item["quantity"] for item in cart)
    return {"items": cart, "total": total}


@router.post("/cart/remove")
@limiter.limit("90/minute")
async def remove_cart(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=128),
    name: str = Query(..., min_length=1, max_length=ITEM_NAME_MAX_LEN),
):
    _validate_session_id(session_id)
    name = _validate_item_name(name)
    return remove_from_cart(session_id, name)


@router.post("/cart/update")
@limiter.limit("90/minute")
async def update_item(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=128),
    name: str = Query(..., min_length=1, max_length=ITEM_NAME_MAX_LEN),
    quantity: int = Query(..., ge=1, le=99),
):
    _validate_session_id(session_id)
    name = _validate_item_name(name)
    return update_cart_item(session_id, name, quantity)


@router.post("/order/checkout")
@limiter.limit("30/minute")
async def checkout(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=128),
):
    _validate_session_id(session_id)
    result = place_order(session_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return {
        "message": "Order placed successfully",
        "order_number": result["order_number"],
        "order_id": result["order_id"],
        "total": result["total"],
        "status": result["status"],
    }


@router.get("/order/status")
@limiter.limit("120/minute")
async def order_status(
    request: Request,
    order_number: str = Query(
        ...,
        min_length=1,
        max_length=64,
        description="Order number e.g. RESTAURANT_1-0001 or numeric id",
    ),
    restaurant_id: str = Query("restaurant_1", min_length=1, max_length=64),
):
    result = get_order_status(order_number, restaurant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.patch("/order/status")
@limiter.limit("60/minute")
async def set_order_status(
    request: Request,
    order_number: str = Query(..., min_length=1, max_length=64),
    status: str = Query(..., min_length=1, max_length=32),
    restaurant_id: str = Query("restaurant_1", min_length=1, max_length=64),
):
    """Update order status (e.g. preparing, ready). For staff/dashboard."""
    result = update_order_status(order_number, status, restaurant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Order not found or invalid status")
    return result
