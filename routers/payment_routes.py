import logging
import os
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from psycopg2.extras import RealDictCursor

from auth import require_api_key
from config import limiter
from database import get_connection
from services.stripe_payment_service import create_payment_intent
from validation import SESSION_ID_MAX_LEN, validate_session_id

logger = logging.getLogger(__name__)


# pydantic model for request body; defines what the /create-intent POST endpoint expects
class CreateIntentBody(BaseModel):
    order_id: int = Field(..., gt=0)
    session_id: str = Field(..., min_length=1, max_length=SESSION_ID_MAX_LEN)

    @field_validator("session_id")
    @classmethod
    def session_id_safe(cls, v: str) -> str:
        return validate_session_id(v)

# creates a router for all /payment endpoints; automatically applies api key check
payment_router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
)

# create stripe payment intent endpoint; limited to 30 api reqs per minute per user
@payment_router.post("/create-intent")
@limiter.limit("30/minute")
async def create_intent(request: Request, body: CreateIntentBody):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, session_id, total,
                       COALESCE(payment_status, 'unpaid') AS payment_status
                FROM orders WHERE id = %s
                """,
                (body.order_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Order not found")
            if row["session_id"] != body.session_id:
                raise HTTPException(status_code=403, detail="Order does not belong to this session")
            if row["payment_status"] == "paid":
                raise HTTPException(status_code=400, detail="Order already paid")
            amount_cents = int(round(float(row["total"]) * 100))
            if amount_cents < 50:
                raise HTTPException(status_code=400, detail="Amount too small for Stripe")
            pi = create_payment_intent(order_id=body.order_id, amount_cents=amount_cents)
            cur.execute(
                """
                UPDATE orders
                SET stripe_payment_intent_id = %s,
                    payment_status = 'processing'
                WHERE id = %s
                """,
                (pi["payment_intent_id"], body.order_id),
            )
    return {"client_secret": pi["client_secret"]}

# creates a seperate route for Stripe webhooks
webhook_router = APIRouter(tags=["stripe-webhook"])
@webhook_router.post("/payments/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias = "stripe-signature"),
):
    payload = await request.body()
    wh_secret = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not wh_secret:
        raise HTTPException(status_code=503, detail="STRIPE_WEBHOOK_SECRET not configured")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature or "",
            secret=wh_secret,
        )
    except Exception as e:
        logger.warning("Webhook verify failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    if event["type"] == "payment_intent.succeeded":
        obj = event["data"]["object"]
        oid = obj.get("metadata", {}).get("order_id")
        if oid:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE orders SET payment_status = 'paid' WHERE id = %s",
                        (int(oid),),
                    )
    return {"received": True}