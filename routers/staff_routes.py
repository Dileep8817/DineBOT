"""Staff/kitchen endpoints.

Separate router, separate secret (X-Staff-Key). Customers get a session-scoped
view of their own order through GET /order/status; everything here reads or
changes the whole restaurant's orders, so none of it may be reachable with the
customer API key.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_staff_key
from config import limiter
from services.order_services import (
    ORDER_STATUSES,
    STATUS_TRANSITIONS,
    InvalidStatusTransition,
    get_order_for_staff,
    list_orders_for_staff,
    next_status,
    update_order_status,
)
from validation import (
    ORDER_REF_MAX_LEN,
    RESTAURANT_ID_MAX_LEN,
    validate_order_reference,
    validate_restaurant_id,
)

logger = logging.getLogger(__name__)

staff_router = APIRouter(
    prefix="/staff",
    tags=["staff"],
    dependencies=[Depends(require_staff_key)],
)

RestaurantId = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN)

# What the dashboard shows by default: everything still in the kitchen.
OPEN_STATUSES = ["pending", "preparing", "ready"]


@staff_router.get("/session")
@limiter.limit("60/minute")
async def staff_session(request: Request):
    """Lets the dashboard check a key before showing the board."""
    return {
        "ok": True,
        "statuses": list(ORDER_STATUSES),
        "transitions": {k: list(v) for k, v in STATUS_TRANSITIONS.items()},
    }


@staff_router.get("/orders")
@limiter.limit("120/minute")
async def staff_orders(
    request: Request,
    restaurant_id: str = RestaurantId,
    status: str = Query(
        None,
        description="Comma-separated statuses. Defaults to pending, preparing and ready.",
    ),
    limit: int = Query(100, ge=1, le=500),
):
    rid = validate_restaurant_id(restaurant_id)
    if status:
        requested = [s.strip().lower() for s in status.split(",") if s.strip()]
        unknown = [s for s in requested if s not in ORDER_STATUSES]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"unknown status: {', '.join(unknown)}. "
                f"Valid: {', '.join(ORDER_STATUSES)}",
            )
        statuses = requested
    else:
        statuses = list(OPEN_STATUSES)

    orders = list_orders_for_staff(rid, statuses=statuses, limit=limit)
    return {
        "restaurant_id": rid,
        "statuses": statuses,
        "orders": [_with_next(o) for o in orders],
    }


@staff_router.get("/orders/{order_number}")
@limiter.limit("120/minute")
async def staff_order(
    request: Request,
    order_number: str,
    restaurant_id: str = RestaurantId,
):
    rid = validate_restaurant_id(restaurant_id)
    order = get_order_for_staff(validate_order_reference(order_number), rid)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _with_next(order)


@staff_router.patch("/orders/{order_number}/status")
@limiter.limit("120/minute")
async def staff_set_order_status(
    request: Request,
    order_number: str,
    restaurant_id: str = RestaurantId,
    status: str = Query(..., min_length=1, max_length=32),
):
    """Advance an order along pending -> preparing -> ready -> completed, or cancel it."""
    rid = validate_restaurant_id(restaurant_id)
    ref = validate_order_reference(order_number)
    try:
        order = update_order_status(ref, status, rid)
    except InvalidStatusTransition as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(e),
                "current_status": e.current,
                "requested_status": e.requested,
                "allowed": e.allowed,
            },
        )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    logger.info(
        "staff_status_change restaurant_id=%s order=%s status=%s", rid, ref, order["status"]
    )
    return _with_next(order)


def _with_next(order: dict) -> dict:
    """Attach the next forward status so the UI does not duplicate the state machine."""
    return {**order, "next_status": next_status(order["status"])}
