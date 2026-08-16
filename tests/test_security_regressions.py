"""Regression tests for the security fixes. Each one fails against the old code."""

import pytest

from services.chat_tools import tool_add_to_cart, tool_get_order_status, tool_update_cart_item
from services.menu_services import get_menu_item
from services.order_services import add_to_cart, get_cart, get_order_status, update_cart_item
from validation import MAX_QUANTITY


# --- IDOR: one customer must not be able to read another customer's order ----


def test_another_session_cannot_read_an_order_over_the_api(
    client, customer_headers, place_order_for, restaurant_id
):
    order = place_order_for("victim_session")

    res = client.get(
        "/order/status",
        params={
            "order_number": order["order_number"],
            "restaurant_id": restaurant_id,
            "session_id": "attacker_session",
        },
        headers=customer_headers,
    )
    assert res.status_code == 404


def test_the_owning_session_can_still_read_its_order(
    client, customer_headers, place_order_for, restaurant_id
):
    order = place_order_for("owner_session")
    res = client.get(
        "/order/status",
        params={
            "order_number": order["order_number"],
            "restaurant_id": restaurant_id,
            "session_id": "owner_session",
        },
        headers=customer_headers,
    )
    assert res.status_code == 200
    assert res.json()["order_number"] == order["order_number"]


def test_order_status_requires_a_session_id(client, customer_headers, restaurant_id):
    """Without this, omitting session_id would fall back to reading any order."""
    res = client.get(
        "/order/status",
        params={"order_number": "RESTAURANT_1-0001", "restaurant_id": restaurant_id},
        headers=customer_headers,
    )
    assert res.status_code == 422


def test_sequential_order_numbers_cannot_be_enumerated(
    client, customer_headers, place_order_for, restaurant_id
):
    """Order numbers are predictable, so scoping is the only thing protecting them."""
    for i in range(3):
        place_order_for(f"other_customer_{i}")

    found = 0
    for n in range(1, 6):
        res = client.get(
            "/order/status",
            params={
                "order_number": f"{restaurant_id.upper()}-{n:04d}",
                "restaurant_id": restaurant_id,
                "session_id": "enumerating_session",
            },
            headers=customer_headers,
        )
        if res.status_code == 200:
            found += 1
    assert found == 0


def test_the_chat_tool_cannot_read_another_sessions_order(place_order_for, restaurant_id):
    order = place_order_for("chat_victim")
    result = tool_get_order_status("chat_attacker", order["order_number"], restaurant_id)
    assert result.get("error")
    assert "items" not in result
    assert result == tool_get_order_status(
        "chat_attacker", order["order_number"], restaurant_id
    )


def test_the_service_layer_requires_a_session_id(place_order_for, restaurant_id):
    order = place_order_for("service_owner")
    with pytest.raises(ValueError):
        get_order_status(order["order_number"], restaurant_id, session_id="")


def test_an_order_of_another_restaurant_is_not_readable(place_order_for):
    order = place_order_for("tenant_owner")
    assert (
        get_order_status(order["order_number"], "other_restaurant", session_id="tenant_owner")
        is None
    )


# --- staff access ------------------------------------------------------------


def test_staff_routes_reject_the_customer_api_key(client, restaurant_id):
    """The customer key is handed to every browser session, so it must not work here."""
    for path, params in (
        ("/staff/orders", {"restaurant_id": restaurant_id}),
        ("/staff/session", {}),
    ):
        res = client.get(path, params=params, headers={"X-API-Key": "test-customer-key"})
        assert res.status_code == 401
        res = client.get(path, params=params, headers={"X-Staff-Key": "test-customer-key"})
        assert res.status_code == 401


def test_staff_can_read_every_order_of_their_restaurant(
    client, staff_headers, place_order_for, restaurant_id
):
    numbers = {place_order_for(f"staff_view_{i}")["order_number"] for i in range(2)}
    res = client.get(
        "/staff/orders", params={"restaurant_id": restaurant_id}, headers=staff_headers
    )
    assert res.status_code == 200
    assert numbers <= {o["order_number"] for o in res.json()["orders"]}


def test_staff_cannot_see_another_restaurants_orders(
    client, staff_headers, place_order_for, restaurant_id
):
    place_order_for("staff_tenant")
    res = client.get(
        "/staff/orders", params={"restaurant_id": "other_restaurant"}, headers=staff_headers
    )
    assert res.status_code == 200
    assert res.json()["orders"] == []


def test_customers_cannot_change_an_order_status(client, customer_headers, place_order_for):
    """The old PATCH /order/status sat behind the customer key."""
    order = place_order_for("status_changer")
    res = client.patch(
        "/order/status",
        params={
            "order_number": order["order_number"],
            "status": "completed",
            "restaurant_id": "restaurant_1",
        },
        headers=customer_headers,
    )
    assert res.status_code in (404, 405)


# --- quantity bounds on the tool path ---------------------------------------


@pytest.mark.parametrize("quantity", [0, -1, -50, 100, 10000])
def test_rest_route_rejects_out_of_bounds_quantities(
    client, customer_headers, restaurant_id, quantity
):
    add_to_cart(
        "bounds_rest", get_menu_item(restaurant_id, "Cheese Pizza"), restaurant_id=restaurant_id
    )
    res = client.post(
        "/cart/update",
        params={
            "session_id": "bounds_rest",
            "restaurant_id": restaurant_id,
            "name": "Cheese Pizza",
            "quantity": quantity,
        },
        headers=customer_headers,
    )
    assert res.status_code == 422
    assert get_cart("bounds_rest", restaurant_id)[0]["quantity"] == 1


@pytest.mark.parametrize("quantity", [0, -1, -50, 100, 10000, "3.5", None])
def test_tool_layer_rejects_out_of_bounds_quantities(restaurant_id, quantity):
    """The LLM tool path bypasses the route's Query(ge=1, le=99) validation."""
    result = tool_add_to_cart("bounds_tool", restaurant_id, "Cheese Pizza", quantity)
    assert result.get("error")
    assert get_cart("bounds_tool", restaurant_id) == []


@pytest.mark.parametrize("quantity", [0, -5, 1000])
def test_tool_update_rejects_out_of_bounds_quantities(restaurant_id, quantity):
    add_to_cart(
        "bounds_update",
        get_menu_item(restaurant_id, "Cheese Pizza"),
        quantity=2,
        restaurant_id=restaurant_id,
    )
    result = tool_update_cart_item("bounds_update", "Cheese Pizza", quantity, restaurant_id)
    assert result.get("error")
    assert get_cart("bounds_update", restaurant_id)[0]["quantity"] == 2


def test_a_negative_quantity_cannot_reach_the_database(restaurant_id):
    with pytest.raises(ValueError):
        add_to_cart(
            "bounds_service",
            get_menu_item(restaurant_id, "Cheese Pizza"),
            quantity=-5,
            restaurant_id=restaurant_id,
        )
    with pytest.raises(ValueError):
        update_cart_item("bounds_service", "Cheese Pizza", MAX_QUANTITY + 1, restaurant_id)
    assert get_cart("bounds_service", restaurant_id) == []


# --- path traversal ---------------------------------------------------------


@pytest.mark.parametrize(
    "restaurant_id", ["../data", "..%2F..%2Fetc", "a/b", "restaurant 1", "x" * 65]
)
def test_restaurant_id_cannot_escape_the_data_directory(
    client, customer_headers, restaurant_id
):
    res = client.get("/menu", params={"restaurant_id": restaurant_id}, headers=customer_headers)
    assert res.status_code in (400, 404, 422)
