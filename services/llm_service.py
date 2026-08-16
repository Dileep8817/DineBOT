# LLM service: OpenAI chat completion with optional tools

import json
import logging
import os
import time

from openai import OpenAI

from config import PROJECT_ROOT  # noqa: F401  importing config loads the project .env

logger = logging.getLogger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "500"))

# OpenAI function-calling tool definitions for the restaurant assistant.
# session_id and restaurant_id are injected by the route when executing.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_menu",
            "description": "Get the full menu for the restaurant.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hours",
            "description": "Get opening and closing hours for the restaurant.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_menu",
            "description": "Search the menu by keyword (e.g. pizza, salad).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search term"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_menu_item",
            "description": "Get details for a specific menu item by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Item name"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a menu item to the customer's cart. Use the exact item name from "
                           "the menu; if several items match, ask which one instead of guessing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "Exact menu item name"},
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity to add (1-99)",
                        "minimum": 1,
                        "maximum": 99,
                        "default": 1,
                    },
                },
                "required": ["item_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cart",
            "description": "Get the current cart contents and totals.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_cart",
            "description": "Clear all items from the cart.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove a specific item from the cart by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Item name to remove"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_cart_item",
            "description": "Set the quantity of an item already in the cart (1-99). To take an "
                           "item out of the cart use remove_from_cart, not quantity 0.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Item name"},
                    "quantity": {
                        "type": "integer",
                        "description": "New quantity (1-99)",
                        "minimum": 1,
                        "maximum": 99,
                    },
                },
                "required": ["name", "quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "checkout_cart",
            "description": "Place the order from the cart; returns order id, order number, "
                            "and total. Payment is completed inside the restaurant app (in-app pay). "
                            "Do not provide external payment URLs.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Get the status of an order placed in this conversation, by order "
                           "number (e.g. RESTAURANT_1-0001) or numeric id. Orders placed by "
                           "other customers are not visible; say so rather than guessing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number_or_id": {"type": "string", "description": "Order number or id"},
                },
                "required": ["order_number_or_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_restaurant_info",
            "description": "Get restaurant name, address, phone, email, delivery/pickup info.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_specials",
            "description": "Get current specials and promotions.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_dietary",
            "description": "Filter menu by dietary option: vegetarian, vegan, gluten-free, dairy-free.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dietary_tag": {
                        "type": "string",
                        "description": "One of: vegetarian, vegan, gluten-free, dairy-free",
                    },
                },
                "required": ["dietary_tag"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allergen_info",
            "description": "Get menu items that contain a specific allergen (dairy, gluten, nuts, fish).",
            "parameters": {
                "type": "object",
                "properties": {
                    "allergen": {"type": "string", "description": "Allergen: dairy, gluten, nuts, fish"},
                },
                "required": ["allergen"],
            },
        },
    },
]


def get_client():
    """Return OpenAI client. Raises ValueError if API key is missing."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise ValueError("OPENAI_API_KEY is not set in environment")
    return OpenAI(api_key=key)


def _serialize_tool_result(value):
    """Convert tool return value to a string for the LLM."""
    if value is None:
        return "No result."
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get("error"):
        return value.get("error", "Error occurred.")
    try:
        return json.dumps(value, default=str)
    except Exception:
        return str(value)


def chat_completion(messages, tools=None):
    """
    Call OpenAI chat completion. Returns (content, tool_calls).
    content: assistant message text (or None if only tool_calls).
    tool_calls: list of {"id", "name", "arguments"} or None.
    On failure, raises; caller can catch and return a safe message.
    """
    client = get_client()
    model = OPENAI_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": OPENAI_MAX_TOKENS,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    start = time.perf_counter()
    response = client.chat.completions.create(**payload)
    elapsed = time.perf_counter() - start
    logger.info("OpenAI chat_completion took %.2fs (model=%s)", elapsed, payload.get("model", ""))

    choice = response.choices[0] if response.choices else None
    if not choice:
        return ("No response from model.", None)

    content = (choice.message.content or "").strip()
    tool_calls = None
    if choice.message.tool_calls:
        tool_calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
            for tc in choice.message.tool_calls
        ]
    return (content, tool_calls)
