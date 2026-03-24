# Restaurant AI Agent

LLM-powered chatbot for restaurants: take orders, answer questions about the menu, hours, and more.

## Setup

### 1. Python

```bash
pip install -r requirements.txt
```

### 2. PostgreSQL

Create a database and set `DATABASE_URL` in `.env` (see `.env.example`). Tables (`cart_items`, `orders`, `order_items`) are created on startup.

### 3. Environment and secrets

Copy `.env.example` to `.env` in the **project root**. Required:

- **`DATABASE_URL`** — PostgreSQL connection string  
- **`API_KEY`** — shared secret; every protected API route requires header `X-API-Key: <your key>`  
- **`OPENAI_API_KEY`** — for `/chat` and optional RAG embeddings  

Never commit `.env`.

### 4. Restaurant data (menu, hours, info, specials)

Real venue data lives under `data/<restaurant_id>/` (gitignored). After cloning:

```bash
mkdir -p data && cp -R sample_data/restaurant_1 data/
```

Edit `data/restaurant_1/*.json` for your venue.

### 5. Run backend

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

`GET /` and `GET /health` are public (no API key). All menu, cart, order, and chat routes require **`X-API-Key`**.

### 6. Run frontend (dev)

The React dev server proxies **`/api/*`** to the backend and adds **`X-API-Key`** from a **server-side** env file so the key is not baked into the JS bundle.

1. Copy `react-frontend/.env.development.example` to `react-frontend/.env.development`.  
2. Set **`DINEBOT_PROXY_API_KEY`** to the **same value** as **`API_KEY`** in the root `.env`.  
3. Start the app:

```bash
cd react-frontend && npm install && npm start
```

The UI calls paths like `/api/menu`; the proxy rewrites them to `http://127.0.0.1:8000/menu` and attaches the key.

### 7. Production / separate API host

There is **no CORS middleware** by design: avoid exposing the API key in the browser.

- Prefer **one origin** (e.g. nginx: `/` → static React, `/api` → FastAPI) and let the **edge** attach `X-API-Key`, or  
- Set **`REACT_APP_API_BASE`** to your API URL only if that API is reachable **without** a browser secret (e.g. public read-only) — not recommended for this app’s write endpoints.

### 8. DineBot logo (widget)

Place your logo at `react-frontend/public/dinebot-logo.png` (optional; text fallback if missing).

## Embeddable widget

- **Widget URL:** `/widget` or `?embed=1` on the app URL.  
- **iframe:** `<iframe src="https://your-frontend-url/widget?restaurant_id=restaurant_1" ...></iframe>`  
- **Query params:** `restaurant_id`, `primary_color`, `restaurant_name`

## Features

- **Menu & search** — Menu, hours, search, dietary/allergen filters  
- **Cart & checkout** — Add/remove/update items; orders stored in PostgreSQL  
- **RAG** — ChromaDB + embeddings for grounded answers  
- **Rate limiting** — SlowAPI per route (e.g. stricter on `/chat`, checkout)  
- **API key auth** — All business routes require `X-API-Key`  
- **Session logging** — Chat logs session id, restaurant id, client IP, duration, tools used, response length  

## API

- **`GET /health`** — DB connectivity (no API key)  
- **`POST /chat`** — Body: `session_id`, `message`, optional `restaurant_id`  
- **`PATCH /order/status`** — Staff order updates  

## Security

- **Secrets:** `.env` gitignored; rotate leaked keys.  
- **Data:** `data/` gitignored; use `sample_data/` as template.  
- **Rate limiting:** SlowAPI (global default + per-route limits).  
- **Validation:** Message length, `session_id`, `restaurant_id`, cart quantities.  
