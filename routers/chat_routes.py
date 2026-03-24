# Chat endpoint: LLM with tool-calling; rate-limited and validated input

import json
import logging
import time

from fastapi import APIRouter, Depends, Request

from auth import require_api_key
from config import limiter
from models.chat_models import ChatRequest

from services.chat_tools import (
    tool_get_menu,
    tool_get_hours,
    tool_search_menu,
    tool_get_menu_item,
    tool_add_to_cart,
    tool_get_cart,
    tool_clear_cart,
    tool_remove_from_cart,
    tool_update_cart_item,
    tool_checkout_cart,
    tool_get_restaurant_info,
    tool_get_specials,
    tool_filter_dietary,
    tool_allergen_info,
    tool_get_order_status,
)
from services.llm_service import chat_completion, TOOLS, _serialize_tool_result
from services.rag_service import retrieve as rag_retrieve

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])

# In-memory conversation history: session_id -> list of OpenAI-format messages (trimmed to last N).
MAX_HISTORY_MESSAGES = 20
_session_history = {}


def _system_message(restaurant_id: str, session_id: str, rag_context: list = None) -> str:
    base = f"""You are a friendly restaurant assistant. You have access to tools for this restaurant.
- restaurant_id for this conversation: {restaurant_id}
- session_id for this conversation: {session_id}
Use these exact IDs when calling any tool that needs them (they will be injected automatically; you only need to provide other parameters like item names, query, order number, etc.).
Help customers with: menu, hours, address, phone, delivery/pickup, specials, dietary options, allergens, adding items to cart, viewing cart, checkout, and order status. Be concise and friendly. 
If a tool returns an error (e.g. item not found), tell the customer and suggest alternatives."""
    if rag_context:
        numbered = "\n".join(f"{i + 1}. {chunk}" for i, chunk in enumerate(rag_context))
        base += "\n\nAnswer using only the information below. Do not invent details.\n\nRestaurant Information:\n" + numbered + "\n\nUse the above when answering the user's question."
    return base



def _run_tool(name: str, arguments: dict, session_id: str, restaurant_id: str):
    """Execute a tool by name with injected session_id and restaurant_id. Returns raw result."""
    args = dict(arguments)
    try:
        if name == "get_menu":
            return tool_get_menu(restaurant_id)
        if name == "get_hours":
            return tool_get_hours(restaurant_id)
        if name == "search_menu":
            return tool_search_menu(restaurant_id, args.get("query", ""))
        if name == "get_menu_item":
            return tool_get_menu_item(restaurant_id, args.get("name", ""))
        if name == "add_to_cart":
            return tool_add_to_cart(
                session_id, restaurant_id,
                args.get("item_name", ""),
                int(args.get("quantity", 1)),
            )
        if name == "get_cart":
            return tool_get_cart(session_id, restaurant_id)
        if name == "clear_cart":
            return tool_clear_cart(session_id, restaurant_id)
        if name == "remove_from_cart":
            return tool_remove_from_cart(session_id, args.get("name", ""), restaurant_id)
        if name == "update_cart_item":
            return tool_update_cart_item(
                session_id, args.get("name", ""), int(args.get("quantity", 1)), restaurant_id
            )
        if name == "checkout_cart":
            return tool_checkout_cart(session_id, restaurant_id)
        if name == "get_order_status":
            return tool_get_order_status(args.get("order_number_or_id", ""), restaurant_id)
        if name == "get_restaurant_info":
            return tool_get_restaurant_info(restaurant_id)
        if name == "get_specials":
            return tool_get_specials(restaurant_id)
        if name == "filter_dietary":
            return tool_filter_dietary(restaurant_id, args.get("dietary_tag", ""))
        if name == "allergen_info":
            return tool_allergen_info(restaurant_id, args.get("allergen", ""))
        return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        logger.exception("Tool %s failed: %s", name, e)
        return {"error": str(e)}


@router.post("/chat")
@limiter.limit("30/minute")
async def chat_endpoint(request: Request, body: ChatRequest):
    session_id = body.session_id
    rid = body.restaurant_id
    message = (body.message or "").strip()
    if not message:
        return {"response": "Send a message to get help.", "cart": _get_cart_for_response(session_id, rid)}

    client_host = request.client.host if request.client else "unknown"
    logger.info(
        "chat_session_start restaurant_id=%s session_id=%s message_len=%d client_ip=%s",
        rid,
        session_id,
        len(message),
        client_host,
    )
    t0 = time.perf_counter()
    tool_rounds = 0
    tools_used: list = []

    # Check if LLM is configured
    try:
        from services.llm_service import get_client
        get_client()
    except ValueError as e:
        logger.warning("LLM not configured: %s", e)
        return {
            "response": "Chat is not configured yet. Please set OPENAI_API_KEY in the server environment.",
            "cart": _get_cart_for_response(session_id, rid),
        }

    # RAG: retrieve relevant chunks for this restaurant and query
    rag_chunks = []
    try:
        rag_chunks = rag_retrieve(rid, message)
    except Exception as e:
        logger.debug("RAG retrieve failed: %s", e)

    # Build message list: system (with optional RAG context) + history + new user message
    system = _system_message(rid, session_id, rag_context=rag_chunks if rag_chunks else None)
    history = _session_history.get(session_id, [])
    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    max_rounds = 5
    final_content = ""
    current_messages = list(messages)

    try:
        for _ in range(max_rounds):
            content, tool_calls = chat_completion(current_messages, tools=TOOLS)

            if tool_calls:
                tool_rounds += 1
                for tc in tool_calls:
                    tools_used.append(tc.get("name", "?"))
                # Append assistant message with tool_calls (OpenAI format)
                assistant_msg = {"role": "assistant", "content": content or None, "tool_calls": []}
                for tc in tool_calls:
                    assistant_msg["tool_calls"].append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    })
                current_messages.append(assistant_msg)

                for tc in tool_calls:
                    try:
                        tool_args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
                    except json.JSONDecodeError:
                        tool_args = {}
                    result = _run_tool(tc["name"], tool_args, session_id, rid)
                    result_str = _serialize_tool_result(result)
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_str,
                    })
                final_content = content or "(One moment...)"
                continue

            final_content = content or "I'm not sure how to help with that. You can ask about the menu, hours, cart, or checkout."
            break
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.exception(
            "chat_session_error restaurant_id=%s session_id=%s duration_ms=%d error=%s",
            rid,
            session_id,
            elapsed_ms,
            e,
        )
        return {
            "response": "Something went wrong. Please try again.",
            "cart": _get_cart_for_response(session_id, rid),
        }

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "chat_session_end restaurant_id=%s session_id=%s duration_ms=%d tool_rounds=%d tools=%s response_len=%d",
        rid,
        session_id,
        elapsed_ms,
        tool_rounds,
        tools_used,
        len(final_content or ""),
    )

    # Persist history: append user and this turn's assistant/tool messages
    turn_messages = []
    for i in range(len(messages), len(current_messages)):
        msg = current_messages[i]
        turn_messages.append(msg)
    history.append({"role": "user", "content": message})
    history.extend(turn_messages)
    # Trim to last N messages (keep pairs; avoid huge context)
    while len(history) > MAX_HISTORY_MESSAGES:
        history.pop(0)
    _session_history[session_id] = history

    # Return cart when relevant (after any cart-affecting turn)
    cart = _get_cart_for_response(session_id, rid)
    return {"response": final_content, "cart": cart}


def _get_cart_for_response(session_id: str, restaurant_id: str):
    """Return current cart for API response (list of {name, price, quantity})."""
    try:
        cart = tool_get_cart(session_id, restaurant_id)
        return cart if isinstance(cart, list) else []
    except Exception:
        return []
