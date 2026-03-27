import os
import stripe

# reads the STRIPE_SECRET_KEY in the .env file and gives it to the environemtn
stripe.api_key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()

# creates a PaymentIntent for the order total in cents
def create_payment_intent(*, order_id : int, amount_cents : int, currency : str = "usd") -> dict:
    if not stripe.api_key:
        raise RuntimeError("STRIPE_SECRET_KEY is not set")
    intent = stripe.PaymentIntent.create(
        amount = amount_cents,
        currency = currency,
        metadata = {"order_id" : str(order_id)},
        automatic_payment_methods={"enabled" : True}
    )
    return {"client_secret" : intent.client_secret, "payment_intent_id" : intent.id}