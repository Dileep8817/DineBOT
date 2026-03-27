# this file outlines the tools the LLM can call on

from services.menu_services import (
    get_menu, get_hours, search_menu, get_menu_item,
    get_restaurant_info, get_specials, filter_menu_by_dietary, get_allergen_info
)
from services.order_services import (
    add_to_cart, get_cart, clear_cart, get_cart_total,
    create_cart, remove_from_cart, update_cart_item, place_order, get_order_status
)

# Menu Service tools
def tool_get_menu(restaurant_id: str):
    return get_menu(restaurant_id)

def tool_get_hours(restaurant_id: str):
    return get_hours(restaurant_id)

def tool_search_menu(restaurant_id: str, query: str):
    return search_menu(restaurant_id, query)

def tool_get_menu_item(restaurant_id: str, name: str):
    return get_menu_item(restaurant_id, name)

# Order Service tools
def tool_create_cart(session_id : str):
    create_cart(session_id)
    return {"message" : f"Cart created for session {session_id}"}

def tool_add_to_cart(session_id: str, restaurant_id: str, item_name: str, quantity: int = 1):
    item = get_menu_item(restaurant_id, item_name)
    if not item:
        return {"error": "Item not found"}
    return add_to_cart(session_id, item, quantity=quantity, restaurant_id=restaurant_id)

def tool_get_cart(session_id: str, restaurant_id: str = "restaurant_1"):
    return get_cart(session_id, restaurant_id)

def tool_clear_cart(session_id: str, restaurant_id: str = "restaurant_1"):
    return clear_cart(session_id, restaurant_id)

def tool_remove_from_cart(session_id: str, name: str, restaurant_id: str = "restaurant_1"):
    return remove_from_cart(session_id, name, restaurant_id)

def tool_update_cart_item(session_id: str, name: str, quantity: int, restaurant_id: str = "restaurant_1"):
    return update_cart_item(session_id, name, quantity, restaurant_id)

def tool_checkout_cart(session_id: str, restaurant_id: str = "restaurant_1"):
    """Creates order from cart, clears cart; returns order_id, order_number, total for in-app payment."""
    result = place_order(session_id, restaurant_id)
    if result.get("error"):
        return result
    return {
        "cart": [],
        "total": result["total"],
        "order_number": result["order_number"],
        "order_id": result["order_id"]
    }

def tool_get_order_status(order_number_or_id: str, restaurant_id: str = "restaurant_1"):
    return get_order_status(order_number_or_id, restaurant_id)


def tool_get_restaurant_info(restaurant_id: str):
    return get_restaurant_info(restaurant_id)


def tool_get_specials(restaurant_id: str):
    return get_specials(restaurant_id)


def tool_filter_dietary(restaurant_id: str, dietary_tag: str):
    return filter_menu_by_dietary(restaurant_id, dietary_tag)


def tool_allergen_info(restaurant_id: str, allergen: str):
    return get_allergen_info(restaurant_id, allergen)
