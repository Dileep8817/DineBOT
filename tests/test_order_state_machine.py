"""Checkout, the order status flow, and the payment status flow."""

import pytest

from database import get_connection
from services.menu_services import get_menu_item
from services.order_services import (
    InvalidStatusTransition,
    add_to_cart,
    get_cart,
    get_order_for_staff,
    next_status,
    update_order_status,
)


def read_payment_status(order_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT payment_status FROM orders WHERE id = %s", (order_id,))
            return cur.fetchone()[0]


# --- checkout ---------------------------------------------------------------


def test_checkout_creates_an_order_and_empties_the_cart(
    client, customer_headers, restaurant_id
):
    add_to_cart(
        "sm_checkout",
        get_menu_item(restaurant_id, "Cheese Pizza"),
        quantity=2,
        restaurant_id=restaurant_id,
    )
    res = client.post(
        "/order/checkout",
        params={"session_id": "sm_checkout", "restaurant_id": restaurant_id},
        headers=customer_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "pending"
    assert body["total"] == pytest.approx(26.0)
    assert body["order_number"].startswith(restaurant_id.upper())
    assert get_cart("sm_checkout", restaurant_id) == []


def test_checkout_with_an_empty_cart_is_rejected(client, customer_headers, restaurant_id):
    res = client.post(
        "/order/checkout",
        params={"session_id": "sm_empty", "restaurant_id": restaurant_id},
        headers=customer_headers,
    )
    assert res.status_code == 400


def test_order_numbers_increase_per_restaurant(place_order_for, restaurant_id):
    first = place_order_for("sm_num_1")
    second = place_order_for("sm_num_2")
    assert first["order_number"] != second["order_number"]
    assert first["order_number"].rsplit("-", 1)[1] < second["order_number"].rsplit("-", 1)[1]


def test_a_new_order_starts_unpaid(place_order_for):
    order = place_order_for("sm_unpaid")
    assert read_payment_status(order["order_id"]) == "unpaid"


# --- order status flow ------------------------------------------------------


def test_full_flow_pending_preparing_ready_completed(place_order_for, restaurant_id):
    number = place_order_for("sm_flow")["order_number"]
    assert get_order_for_staff(number, restaurant_id)["status"] == "pending"
    for status in ("preparing", "ready", "completed"):
        assert update_order_status(number, status, restaurant_id)["status"] == status


def test_next_status_follows_the_flow():
    assert next_status("pending") == "preparing"
    assert next_status("preparing") == "ready"
    assert next_status("ready") == "completed"
    assert next_status("completed") is None
    assert next_status("cancelled") is None


@pytest.mark.parametrize(
    "path, requested",
    [
        ([], "ready"),  # pending -> ready skips the kitchen
        ([], "completed"),  # pending -> completed skips everything
        (["preparing", "ready", "completed"], "pending"),  # reopen a completed order
        (["preparing", "ready", "completed"], "cancelled"),  # cancel after completion
        (["cancelled"], "preparing"),  # revive a cancelled order
    ],
)
def test_out_of_flow_transitions_are_refused(
    place_order_for, restaurant_id, path, requested
):
    number = place_order_for(f"sm_bad_{requested}_{len(path)}")["order_number"]
    for status in path:
        update_order_status(number, status, restaurant_id)
    before = get_order_for_staff(number, restaurant_id)["status"]

    with pytest.raises(InvalidStatusTransition):
        update_order_status(number, requested, restaurant_id)

    assert get_order_for_staff(number, restaurant_id)["status"] == before


def test_cancel_is_allowed_before_ready(place_order_for, restaurant_id):
    number = place_order_for("sm_cancel")["order_number"]
    assert update_order_status(number, "cancelled", restaurant_id)["status"] == "cancelled"


def test_repeating_the_current_status_is_a_no_op(place_order_for, restaurant_id):
    number = place_order_for("sm_repeat")["order_number"]
    update_order_status(number, "preparing", restaurant_id)
    assert update_order_status(number, "preparing", restaurant_id)["status"] == "preparing"


def test_unknown_status_is_rejected(place_order_for, restaurant_id):
    number = place_order_for("sm_unknown")["order_number"]
    with pytest.raises(ValueError):
        update_order_status(number, "on_fire", restaurant_id)


def test_updating_an_order_of_another_restaurant_finds_nothing(place_order_for):
    number = place_order_for("sm_tenant")["order_number"]
    assert update_order_status(number, "preparing", "other_restaurant") is None


def test_staff_route_reports_an_out_of_flow_change_as_409(
    client, staff_headers, place_order_for, restaurant_id
):
    number = place_order_for("sm_409")["order_number"]
    res = client.patch(
        f"/staff/orders/{number}/status",
        params={"restaurant_id": restaurant_id, "status": "completed"},
        headers=staff_headers,
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["current_status"] == "pending"
    assert detail["allowed"] == ["preparing", "cancelled"]


def test_staff_route_advances_an_order(
    client, staff_headers, place_order_for, restaurant_id
):
    number = place_order_for("sm_advance")["order_number"]
    res = client.patch(
        f"/staff/orders/{number}/status",
        params={"restaurant_id": restaurant_id, "status": "preparing"},
        headers=staff_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "preparing"
    assert body["next_status"] == "ready"


def test_staff_route_404s_for_an_unknown_order(client, staff_headers, restaurant_id):
    res = client.patch(
        "/staff/orders/RESTAURANT_1-999999/status",
        params={"restaurant_id": restaurant_id, "status": "preparing"},
        headers=staff_headers,
    )
    assert res.status_code == 404


# --- payment status flow ----------------------------------------------------


@pytest.fixture()
def fake_stripe(monkeypatch):
    """Stand in for Stripe so the payment flow can be tested without the network."""
    calls = []

    def create_payment_intent(order_id, amount_cents):
        calls.append({"order_id": order_id, "amount_cents": amount_cents})
        return {
            "payment_intent_id": f"pi_test_{order_id}",
            "client_secret": f"pi_test_{order_id}_secret",
        }

    monkeypatch.setattr(
        "routers.payment_routes.create_payment_intent", create_payment_intent
    )
    return calls


def test_create_intent_moves_the_order_to_processing(
    client, customer_headers, place_order_for, fake_stripe
):
    order = place_order_for("sm_pay", quantity=2)
    res = client.post(
        "/payments/create-intent",
        json={"order_id": order["order_id"], "session_id": "sm_pay"},
        headers=customer_headers,
    )
    assert res.status_code == 200
    assert res.json()["client_secret"].startswith("pi_test_")
    assert fake_stripe[0]["amount_cents"] == 2600
    assert read_payment_status(order["order_id"]) == "processing"


def test_create_intent_rejects_another_session(
    client, customer_headers, place_order_for, fake_stripe
):
    order = place_order_for("sm_pay_owner")
    res = client.post(
        "/payments/create-intent",
        json={"order_id": order["order_id"], "session_id": "sm_pay_attacker"},
        headers=customer_headers,
    )
    assert res.status_code == 403
    assert fake_stripe == []
    assert read_payment_status(order["order_id"]) == "unpaid"


def test_create_intent_refuses_an_order_already_paid(
    client, customer_headers, place_order_for, fake_stripe
):
    order = place_order_for("sm_paid")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET payment_status = 'paid' WHERE id = %s",
                (order["order_id"],),
            )
    res = client.post(
        "/payments/create-intent",
        json={"order_id": order["order_id"], "session_id": "sm_paid"},
        headers=customer_headers,
    )
    assert res.status_code == 400
    assert fake_stripe == []


def test_create_intent_404s_for_an_unknown_order(client, customer_headers, fake_stripe):
    res = client.post(
        "/payments/create-intent",
        json={"order_id": 999999, "session_id": "sm_pay_missing"},
        headers=customer_headers,
    )
    assert res.status_code == 404


def test_webhook_requires_a_configured_secret(client, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    res = client.post("/payments/webhook", content=b"{}")
    assert res.status_code == 503


def test_webhook_rejects_an_unsigned_payload(client, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    res = client.post("/payments/webhook", content=b'{"type":"payment_intent.succeeded"}')
    assert res.status_code == 400


@pytest.fixture()
def signed_webhook(client, monkeypatch):
    """Deliver a webhook event with signature verification stubbed out."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

    def deliver(event_type, order_id):
        event = {
            "type": event_type,
            "data": {"object": {"metadata": {"order_id": str(order_id)}}},
        }
        monkeypatch.setattr(
            "stripe.Webhook.construct_event", lambda payload, sig_header, secret: event
        )
        return client.post(
            "/payments/webhook", content=b"{}", headers={"stripe-signature": "t=1,v1=x"}
        )

    return deliver


@pytest.mark.parametrize(
    "event_type, expected",
    [
        ("payment_intent.succeeded", "paid"),
        ("payment_intent.payment_failed", "failed"),
        ("payment_intent.canceled", "unpaid"),
        ("payment_intent.created", "processing"),  # not acted on
    ],
)
def test_webhook_settles_the_payment_status(
    client, customer_headers, place_order_for, fake_stripe, signed_webhook, event_type, expected
):
    session = "sm_hook_" + event_type.replace(".", "_")
    order = place_order_for(session)
    res = client.post(
        "/payments/create-intent",
        json={"order_id": order["order_id"], "session_id": session},
        headers=customer_headers,
    )
    assert res.status_code == 200
    assert signed_webhook(event_type, order["order_id"]).status_code == 200
    assert read_payment_status(order["order_id"]) == expected


def test_a_failed_payment_can_be_retried(
    client, customer_headers, place_order_for, fake_stripe, signed_webhook
):
    order = place_order_for("sm_retry")
    client.post(
        "/payments/create-intent",
        json={"order_id": order["order_id"], "session_id": "sm_retry"},
        headers=customer_headers,
    )
    signed_webhook("payment_intent.payment_failed", order["order_id"])

    res = client.post(
        "/payments/create-intent",
        json={"order_id": order["order_id"], "session_id": "sm_retry"},
        headers=customer_headers,
    )
    assert res.status_code == 200
    assert read_payment_status(order["order_id"]) == "processing"


def test_a_paid_order_appears_in_the_staff_stream_window(
    client, customer_headers, staff_headers, place_order_for, restaurant_id, fake_stripe, signed_webhook
):
    """The stream polls updated_at, so settling a payment has to move it."""
    order = place_order_for("sm_hook_stream")
    before = client.get(
        "/staff/orders", params={"restaurant_id": restaurant_id}, headers=staff_headers
    ).json()["orders"]
    stamp = next(o["updated_at"] for o in before if o["order_number"] == order["order_number"])

    client.post(
        "/payments/create-intent",
        json={"order_id": order["order_id"], "session_id": "sm_hook_stream"},
        headers=customer_headers,
    )
    signed_webhook("payment_intent.succeeded", order["order_id"])

    after = client.get(
        "/staff/orders", params={"restaurant_id": restaurant_id}, headers=staff_headers
    ).json()["orders"]
    updated = next(o for o in after if o["order_number"] == order["order_number"])
    assert updated["payment_status"] == "paid"
    assert updated["updated_at"] > stamp


def test_payment_status_is_reported_to_the_customer(
    client, customer_headers, place_order_for, restaurant_id
):
    order = place_order_for("sm_report")
    res = client.get(
        "/order/status",
        params={
            "order_number": order["order_number"],
            "restaurant_id": restaurant_id,
            "session_id": "sm_report",
        },
        headers=customer_headers,
    )
    assert res.status_code == 200
    assert res.json()["payment_status"] == "unpaid"
