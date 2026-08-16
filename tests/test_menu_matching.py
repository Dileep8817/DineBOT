"""Menu item name resolution: exact, unique-substring, and ambiguity."""

import pytest

from services.chat_tools import tool_add_to_cart, tool_get_menu_item
from services.menu_services import AmbiguousMenuItem, get_menu_item
from services.order_services import get_cart


def test_exact_match_is_case_and_whitespace_insensitive(restaurant_id):
    for query in ("Cheese Pizza", "cheese pizza", "  CHEESE PIZZA  "):
        assert get_menu_item(restaurant_id, query)["name"] == "Cheese Pizza"


def test_a_unique_substring_matches(restaurant_id):
    assert get_menu_item(restaurant_id, "sorbet")["name"] == "Placeholder Fruit Sorbet"


def test_an_ambiguous_substring_raises_with_the_candidates(restaurant_id):
    with pytest.raises(AmbiguousMenuItem) as excinfo:
        get_menu_item(restaurant_id, "pizza")
    assert sorted(excinfo.value.matches) == ["Cheese Pizza", "Veggie Pizza"]


def test_an_exact_name_wins_over_being_a_substring_of_others(restaurant_id):
    """'Cheese Pizza' is also a substring candidate, so the exact match must win."""
    assert get_menu_item(restaurant_id, "Cheese Pizza")["name"] == "Cheese Pizza"


def test_no_match_returns_none(restaurant_id):
    assert get_menu_item(restaurant_id, "Sushi Platter") is None


def test_an_empty_name_is_rejected(restaurant_id):
    with pytest.raises(ValueError):
        get_menu_item(restaurant_id, "   ")


def test_an_ambiguous_name_is_not_silently_added_to_the_cart(restaurant_id):
    """The old matcher charged for whichever pizza came first in menu.json."""
    result = tool_add_to_cart("ambiguous_cart", restaurant_id, "pizza", 1)
    assert result.get("error")
    assert sorted(result["options"]) == ["Cheese Pizza", "Veggie Pizza"]
    assert get_cart("ambiguous_cart", restaurant_id) == []


def test_the_menu_item_tool_reports_the_candidates(restaurant_id):
    result = tool_get_menu_item(restaurant_id, "pizza")
    assert sorted(result["options"]) == ["Cheese Pizza", "Veggie Pizza"]


def test_the_menu_item_route_returns_409_with_the_candidates(
    client, customer_headers, restaurant_id
):
    res = client.get(
        "/menu-item",
        params={"restaurant_id": restaurant_id, "name": "pizza"},
        headers=customer_headers,
    )
    assert res.status_code == 409
    assert sorted(res.json()["matches"]) == ["Cheese Pizza", "Veggie Pizza"]


def test_the_cart_add_route_returns_409_for_an_ambiguous_name(
    client, customer_headers, restaurant_id
):
    res = client.post(
        "/cart/add",
        params={
            "session_id": "ambiguous_route",
            "restaurant_id": restaurant_id,
            "name": "pizza",
        },
        headers=customer_headers,
    )
    assert res.status_code == 409
    assert get_cart("ambiguous_route", restaurant_id) == []


def test_an_exact_name_still_adds_to_the_cart(client, customer_headers, restaurant_id):
    res = client.post(
        "/cart/add",
        params={
            "session_id": "exact_route",
            "restaurant_id": restaurant_id,
            "name": "Veggie Pizza",
        },
        headers=customer_headers,
    )
    assert res.status_code == 200
    cart = get_cart("exact_route", restaurant_id)
    assert [item["name"] for item in cart] == ["Veggie Pizza"]
    assert cart[0]["price"] == 15.0


def test_a_missing_restaurant_reports_which_file_is_missing(client, customer_headers):
    res = client.get(
        "/menu", params={"restaurant_id": "no_such_restaurant"}, headers=customer_headers
    )
    assert res.status_code == 404
    assert "menu.json" in res.json()["detail"]
