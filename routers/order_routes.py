# Order and cart API with validation, API key, and rate limiting

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
from validation import (
    ITEM_NAME_MAX_LEN,
    MAX_QUANTITY,
    MIN_QUANTITY,
    ORDER_REF_MAX_LEN,
    RESTAURANT_ID_MAX_LEN,
    SESSION_ID_MAX_LEN,
    validate_item_name,
    validate_order_reference,
    validate_quantity,
    validate_restaurant_id,
    validate_session_id,
)

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/cart/add")
@limiter.limit("90/minute")
async def add_item(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=SESSION_ID_MAX_LEN),
    name: str = Query(..., min_length=1, max_length=ITEM_NAME_MAX_LEN),
    restaurant_id: str = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN),
):
    session_id = validate_session_id(session_id)
    rid = validate_restaurant_id(restaurant_id)
    name = validate_item_name(name)
    item = get_menu_item(rid, name)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    add_to_cart(session_id, item, restaurant_id=rid)
    return {"message": f"{name} added to cart"}


@router.get("/cart")
@limiter.limit("120/minute")
async def cart(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=SESSION_ID_MAX_LEN),
    restaurant_id: str = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN),
):
    session_id = validate_session_id(session_id)
    rid = validate_restaurant_id(restaurant_id)
    return get_cart(session_id, rid)


@router.post("/cart/clear")
@limiter.limit("60/minute")
async def clear(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=SESSION_ID_MAX_LEN),
    restaurant_id: str = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN),
):
    session_id = validate_session_id(session_id)
    rid = validate_restaurant_id(restaurant_id)
    return clear_cart(session_id, rid)


@router.get("/cart/summary")
@limiter.limit("120/minute")
async def cart_summary(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=SESSION_ID_MAX_LEN),
    restaurant_id: str = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN),
):
    session_id = validate_session_id(session_id)
    rid = validate_restaurant_id(restaurant_id)
    cart = get_cart(session_id, rid)
    total = sum(item["price"] * item["quantity"] for item in cart)
    return {"items": cart, "total": total}


@router.post("/cart/remove")
@limiter.limit("90/minute")
async def remove_cart(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=SESSION_ID_MAX_LEN),
    name: str = Query(..., min_length=1, max_length=ITEM_NAME_MAX_LEN),
    restaurant_id: str = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN),
):
    session_id = validate_session_id(session_id)
    rid = validate_restaurant_id(restaurant_id)
    name = validate_item_name(name)
    return remove_from_cart(session_id, name, rid)


@router.post("/cart/update")
@limiter.limit("90/minute")
async def update_item(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=SESSION_ID_MAX_LEN),
    name: str = Query(..., min_length=1, max_length=ITEM_NAME_MAX_LEN),
    quantity: int = Query(..., ge=MIN_QUANTITY, le=MAX_QUANTITY),
    restaurant_id: str = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN),
):
    session_id = validate_session_id(session_id)
    rid = validate_restaurant_id(restaurant_id)
    name = validate_item_name(name)
    return update_cart_item(session_id, name, validate_quantity(quantity), rid)


@router.post("/order/checkout")
@limiter.limit("30/minute")
async def checkout(
    request: Request,
    session_id: str = Query(..., min_length=1, max_length=SESSION_ID_MAX_LEN),
    restaurant_id: str = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN),
):
    session_id = validate_session_id(session_id)
    rid = validate_restaurant_id(restaurant_id)
    result = place_order(session_id, rid)
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
        max_length=ORDER_REF_MAX_LEN,
        description="Order number e.g. RESTAURANT_1-0001 or numeric id",
    ),
    restaurant_id: str = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN),
    session_id: str = Query(
        ...,
        min_length=1,
        max_length=SESSION_ID_MAX_LEN,
        description="Session that placed the order; orders from other sessions are not visible",
    ),
):
    """Customer view of one of their own orders. Staff use GET /staff/orders."""
    session_id = validate_session_id(session_id)
    rid = validate_restaurant_id(restaurant_id)
    order_ref = validate_order_reference(order_number)
    result = get_order_status(order_ref, rid, session_id=session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.patch("/order/status")
@limiter.limit("60/minute")
async def set_order_status(
    request: Request,
    order_number: str = Query(..., min_length=1, max_length=ORDER_REF_MAX_LEN),
    status: str = Query(..., min_length=1, max_length=32),
    restaurant_id: str = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN),
):
    """Update order status (e.g. preparing, ready). For staff/dashboard."""
    rid = validate_restaurant_id(restaurant_id)
    order_ref = validate_order_reference(order_number)
    result = update_order_status(order_ref, status, rid)
    if not result:
        raise HTTPException(status_code=404, detail="Order not found or invalid status")
    return result
