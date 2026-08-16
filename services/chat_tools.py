# this file outlines the tools the LLM can call on

from services.menu_services import (
    get_menu, get_hours, search_menu, get_menu_item, AmbiguousMenuItem,
    get_restaurant_info, get_specials, filter_menu_by_dietary, get_allergen_info
)
from services.order_services import (
    add_to_cart, get_cart, clear_cart,
    remove_from_cart, update_cart_item, place_order, get_order_status
)
from validation import validate_item_name, validate_quantity

# Menu Service tools
def tool_get_menu(restaurant_id: str):
    return get_menu(restaurant_id)

def tool_get_hours(restaurant_id: str):
    return get_hours(restaurant_id)

def tool_search_menu(restaurant_id: str, query: str):
    return search_menu(restaurant_id, query)

def tool_get_menu_item(restaurant_id: str, name: str):
    try:
        item = get_menu_item(restaurant_id, name)
    except AmbiguousMenuItem as e:
        return {"error": str(e), "options": e.matches}
    except ValueError as e:
        return {"error": str(e)}
    if not item:
        return {"error": f"No menu item matches {name!r}."}
    return item

# Order Service tools
def tool_add_to_cart(session_id: str, restaurant_id: str, item_name: str, quantity: int = 1):
    try:
        item_name = validate_item_name(item_name)
        quantity = validate_quantity(quantity)
    except ValueError as e:
        return {"error": str(e)}
    try:
        item = get_menu_item(restaurant_id, item_name)
    except AmbiguousMenuItem as e:
        # Never guess: charging for the wrong dish is worse than one more question.
        return {"error": str(e), "options": e.matches}
    if not item:
        return {"error": f"No menu item matches {item_name!r}."}
    return add_to_cart(session_id, item, quantity=quantity, restaurant_id=restaurant_id)

def tool_get_cart(session_id: str, restaurant_id: str):
    return get_cart(session_id, restaurant_id)

def tool_clear_cart(session_id: str, restaurant_id: str):
    return clear_cart(session_id, restaurant_id)

def tool_remove_from_cart(session_id: str, name: str, restaurant_id: str):
    try:
        name = validate_item_name(name)
    except ValueError as e:
        return {"error": str(e)}
    return remove_from_cart(session_id, name, restaurant_id)

def tool_update_cart_item(session_id: str, name: str, quantity: int, restaurant_id: str):
    try:
        name = validate_item_name(name)
        quantity = validate_quantity(quantity)
    except ValueError as e:
        return {"error": str(e)}
    return update_cart_item(session_id, name, quantity, restaurant_id)

def tool_checkout_cart(session_id: str, restaurant_id: str):
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

def tool_get_order_status(session_id: str, order_number_or_id: str, restaurant_id: str):
    """Look up an order the current chat session placed. Other sessions' orders are invisible."""
    order = get_order_status(order_number_or_id, restaurant_id, session_id=session_id)
    if not order:
        return {"error": "No order with that number was placed in this conversation."}
    return order


def tool_get_restaurant_info(restaurant_id: str):
    return get_restaurant_info(restaurant_id)


def tool_get_specials(restaurant_id: str):
    return get_specials(restaurant_id)


def tool_filter_dietary(restaurant_id: str, dietary_tag: str):
    return filter_menu_by_dietary(restaurant_id, dietary_tag)


def tool_allergen_info(restaurant_id: str, allergen: str):
    return get_allergen_info(restaurant_id, allergen)
