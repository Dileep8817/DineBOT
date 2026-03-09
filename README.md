# Restaurant AI Agent

LLM-powered chatbot for restaurants: take orders, answer questions about the menu, hours, and more.

## Setup

### 1. Python

```bash
pip install -r requirements.txt
```

### 2. PostgreSQL

Create a database and set the connection URL:

```bash
# Example: create database (run in psql or pgAdmin)
createdb restaurant_ai

# Set env (or copy .env.example to .env)
export DATABASE_URL=postgresql://localhost/restaurant_ai
# Or with user/password:
# export DATABASE_URL=postgresql://user:password@localhost:5432/restaurant_ai
```

Tables (`cart_items`, `orders`, `order_items`) are created automatically on first run.

### 3. Run backend

```bash
uvicorn main:app --reload
```

### 4. Run frontend

```bash
cd react-frontend && npm install && npm start
```

### 5. DineBot logo (widget)

The embeddable widget uses the DineBot logo as the clickable button. Copy your logo image to:

```
react-frontend/public/dinebot-logo.png
```

If the file is missing, the button shows the text “DineBot” as a fallback.

## Embeddable widget

Restaurants can embed the chat widget on their site:

- **Widget URL:** Open `/widget` or add `?embed=1` to the app URL (e.g. `http://localhost:3000/widget` or `http://localhost:3000/?embed=1`).
- **iframe:** Use  
  `<iframe src="https://your-frontend-url/widget?restaurant_id=restaurant_1" width="400" height="600" style="border:none;"></iframe>`  
  (Replace `your-frontend-url` with your deployed React app URL.)
- **Query params:** `restaurant_id` (default `restaurant_1`), `primary_color` (e.g. `%23c45c26` for #c45c26), `restaurant_name` (header title).

The widget shows a floating DineBot logo; clicking it opens a panel with Chat (with quick prompts), Menu, and Cart tabs. After checkout, an order confirmation strip appears.

## Features

- **Menu & search** – Menu, hours, search, dietary/allergen filters
- **Cart & checkout** – Add/remove/update items; checkout creates a persistent order with order number
- **Order status** – Track by order number (e.g. `RESTAURANT_1-0001`)
- **Reservations** – e.g. “reserve for 2 on 2025-03-15 at 18:00”
- **Delivery / pickup** – Info from restaurant `info.json`
- **Specials** – Daily and ongoing promos

All cart and order data is stored in PostgreSQL.

## API

- **Health:** `GET /health` returns `{"status":"ok","database":"connected"}` or 503 if DB is down.
- **Chat** accepts optional `restaurant_id` in the body (default `restaurant_1`). All tools are scoped by it.
- **Order status (staff):** `PATCH /order/status?order_number=RESTAURANT_1-0001&status=preparing` to update status (`pending`, `preparing`, `ready`, `completed`, `cancelled`).

## Production

- Set **CORS_ORIGINS** (comma-separated) in `.env` for your frontend and embed domains.
- In **react-frontend**, set **REACT_APP_API_BASE** to your API URL (e.g. `https://api.yourdomain.com`).
- Chat requests are logged (restaurant_id, session_id, message length) for debugging and analytics.

## Security

- **Rate limiting:** `POST /chat` is limited to 30 requests/minute per IP (SlowAPI).
- **Input validation:** Chat message length (1–2000 chars), session_id format, cart quantity (1–99), and `restaurant_id` (path traversal prevented).
- **Optional API key:** Set `API_KEY` or `API_KEYS` in `.env` and use `Depends(verify_api_key)` on admin routes (see `auth.py`).
