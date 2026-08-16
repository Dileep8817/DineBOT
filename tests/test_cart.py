"""Cart add / update / remove, over the REST routes and the service layer."""

import pytest

from services.order_services import (
    add_to_cart,
    clear_cart,
    get_cart,
    get_cart_total,
    remove_from_cart,
    update_cart_item,
)
from services.menu_services import get_menu_item
from validation import MAX_QUANTITY


def cart_params(session_id, restaurant_id, **extra):
    return {"session_id": session_id, "restaurant_id": restaurant_id, **extra}


def test_add_then_read_cart(client, customer_headers, restaurant_id):
    params = cart_params("cart_add", restaurant_id, name="Cheese Pizza")
    res = client.post("/cart/add", params=params, headers=customer_headers)
    assert res.status_code == 200

    res = client.get(
        "/cart", params=cart_params("cart_add", restaurant_id), headers=customer_headers
    )
    assert res.status_code == 200
    assert res.json() == [{"name": "Cheese Pizza", "price": 13.0, "quantity": 1}]


def test_the_add_route_honours_quantity(client, customer_headers, restaurant_id):
    """It used to ignore the parameter and add one, including for quantity=500."""
    res = client.post(
        "/cart/add",
        params=cart_params("cart_add_qty", restaurant_id, name="Cheese Pizza", quantity=3),
        headers=customer_headers,
    )
    assert res.status_code == 200
    assert res.json()["quantity"] == 3
    assert get_cart("cart_add_qty", restaurant_id)[0]["quantity"] == 3


@pytest.mark.parametrize("quantity", [0, -2, MAX_QUANTITY + 1, 500])
def test_the_add_route_bounds_quantity(client, customer_headers, restaurant_id, quantity):
    res = client.post(
        "/cart/add",
        params=cart_params(
            "cart_add_bounds", restaurant_id, name="Cheese Pizza", quantity=quantity
        ),
        headers=customer_headers,
    )
    assert res.status_code == 422
    assert get_cart("cart_add_bounds", restaurant_id) == []


def test_the_add_route_reports_the_resolved_item_name(
    client, customer_headers, restaurant_id
):
    """Adding "sorbet" must say which item was billed, not echo the query."""
    res = client.post(
        "/cart/add",
        params=cart_params("cart_add_name", restaurant_id, name="sorbet"),
        headers=customer_headers,
    )
    assert res.json()["name"] == "Placeholder Fruit Sorbet"
    assert "Placeholder Fruit Sorbet" in res.json()["message"]


def test_adding_the_same_item_twice_increases_the_quantity(restaurant_id):
    item = get_menu_item(restaurant_id, "Cheese Pizza")
    add_to_cart("cart_twice", item, quantity=2, restaurant_id=restaurant_id)
    cart = add_to_cart("cart_twice", item, quantity=3, restaurant_id=restaurant_id)
    assert cart == [{"name": "Cheese Pizza", "price": 13.0, "quantity": 5}]


def test_accumulated_quantity_is_capped(restaurant_id):
    item = get_menu_item(restaurant_id, "Cheese Pizza")
    for _ in range(3):
        cart = add_to_cart("cart_cap", item, quantity=MAX_QUANTITY, restaurant_id=restaurant_id)
    assert cart[0]["quantity"] == MAX_QUANTITY


def test_update_quantity(client, customer_headers, restaurant_id):
    client.post(
        "/cart/add",
        params=cart_params("cart_update", restaurant_id, name="Cheese Pizza"),
        headers=customer_headers,
    )
    res = client.post(
        "/cart/update",
        params=cart_params("cart_update", restaurant_id, name="cheese pizza", quantity=4),
        headers=customer_headers,
    )
    assert res.status_code == 200
    assert res.json()[0]["quantity"] == 4


def test_update_is_case_insensitive_and_leaves_other_items_alone(restaurant_id):
    for name in ("Cheese Pizza", "Sample Fries"):
        add_to_cart(
            "cart_case", get_menu_item(restaurant_id, name), restaurant_id=restaurant_id
        )
    update_cart_item("cart_case", "SAMPLE FRIES", 7, restaurant_id)
    quantities = {item["name"]: item["quantity"] for item in get_cart("cart_case", restaurant_id)}
    assert quantities == {"Cheese Pizza": 1, "Sample Fries": 7}


def test_remove_item(client, customer_headers, restaurant_id):
    for name in ("Cheese Pizza", "Sample Fries"):
        client.post(
            "/cart/add",
            params=cart_params("cart_remove", restaurant_id, name=name),
            headers=customer_headers,
        )
    res = client.post(
        "/cart/remove",
        params=cart_params("cart_remove", restaurant_id, name="Cheese Pizza"),
        headers=customer_headers,
    )
    assert res.status_code == 200
    assert [item["name"] for item in res.json()] == ["Sample Fries"]


def test_removing_an_item_that_is_not_there_is_not_an_error(restaurant_id):
    assert remove_from_cart("cart_missing", "Cheese Pizza", restaurant_id) == []


def test_cart_summary_totals(client, customer_headers, restaurant_id):
    add_to_cart(
        "cart_total",
        get_menu_item(restaurant_id, "Cheese Pizza"),
        quantity=2,
        restaurant_id=restaurant_id,
    )
    add_to_cart(
        "cart_total",
        get_menu_item(restaurant_id, "Sample Fries"),
        restaurant_id=restaurant_id,
    )
    res = client.get(
        "/cart/summary",
        params=cart_params("cart_total", restaurant_id),
        headers=customer_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == pytest.approx(31.0)  # 13*2 + 5
    assert get_cart_total("cart_total", restaurant_id) == pytest.approx(31.0)


def test_clear_cart(client, customer_headers, restaurant_id):
    add_to_cart(
        "cart_clear", get_menu_item(restaurant_id, "Cheese Pizza"), restaurant_id=restaurant_id
    )
    res = client.post(
        "/cart/clear", params=cart_params("cart_clear", restaurant_id), headers=customer_headers
    )
    assert res.status_code == 200
    assert get_cart("cart_clear", restaurant_id) == []


def test_carts_are_isolated_per_session_and_restaurant(restaurant_id):
    item = get_menu_item(restaurant_id, "Cheese Pizza")
    add_to_cart("cart_a", item, restaurant_id=restaurant_id)
    assert get_cart("cart_b", restaurant_id) == []
    # Same session id, different restaurant: separate cart.
    add_to_cart("cart_a", {"name": "Other Item", "price": 5.0}, restaurant_id="other_restaurant")
    assert [i["name"] for i in get_cart("cart_a", restaurant_id)] == ["Cheese Pizza"]
    assert [i["name"] for i in get_cart("cart_a", "other_restaurant")] == ["Other Item"]
    clear_cart("cart_a", "other_restaurant")


def test_unknown_item_is_a_404(client, customer_headers, restaurant_id):
    res = client.post(
        "/cart/add",
        params=cart_params("cart_404", restaurant_id, name="Sushi Platter"),
        headers=customer_headers,
    )
    assert res.status_code == 404


def test_cart_requires_an_api_key(client, restaurant_id):
    res = client.get("/cart", params=cart_params("cart_noauth", restaurant_id))
    assert res.status_code == 401
