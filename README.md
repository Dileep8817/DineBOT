# Restaurant AI Agent

LLM-powered chatbot for restaurants: take orders, answer questions about the menu, hours, and more.

## Setup

### 1. Python

```bash
pip install -r requirements.txt
```

### 2. PostgreSQL

Create a database and set **`DATABASE_URL`** in `.env` (see `.env.example`). Cart and order tables are created on startup.

```bash
createdb restaurant_ai
# DATABASE_URL=postgresql://YOUR_USER@localhost:5432/restaurant_ai
```

### 3. Environment and secrets

Copy `.env.example` to `.env` in the **project root** (never commit `.env`).

- **`DATABASE_URL`** — **required** (PostgreSQL only).  
- **`OPENAI_API_KEY`** — required for `/chat` (and RAG embeddings if used).  
- **`API_KEY`** — optional locally: if unset, server uses **`dinebot-local-dev`** (same as `react-frontend/.env.development`). Use a strong key in production.

Protected routes require **`X-API-Key`** (the React dev proxy adds it for `/api/*`).

### 4. Restaurant data (menu, hours, info, specials)

Real venue data lives under **`data/<restaurant_id>/`** (gitignored — not in the remote repo). After cloning, create that tree locally and add your own JSON files (see **`docs/RESTAURANT_DATA.md`** for layout). Use a private backup or export; do not rely on the repo for menu content.

### 5. Run backend

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

`GET /` and `GET /health` are public (no API key). All menu, cart, order, and chat routes require **`X-API-Key`**.

### 6. Run frontend (dev)

`react-frontend/.env.development` sets **`DINEBOT_PROXY_API_KEY=dinebot-local-dev`** by default. If you set **`API_KEY`** in the root `.env`, use the same value in **`DINEBOT_PROXY_API_KEY`**.

```bash
cd react-frontend && npm install && npm start
```

The UI calls `/api/menu`, etc.; the proxy forwards to `http://127.0.0.1:8000` and attaches the key.

### 7. Production / separate API host

There is **no CORS middleware**. Prefer one origin (e.g. nginx) or an edge that adds **`X-API-Key`**.

### 8. DineBot logo (widget)

Optional: `react-frontend/public/dinebot-logo.png`

## Embeddable widget

- **Widget URL:** `/widget` or `?embed=1`  
- **iframe:** `<iframe src="https://your-frontend-url/widget?restaurant_id=restaurant_1" ...></iframe>`  
- **Query params:** `restaurant_id`, `primary_color`, `restaurant_name`

## Features

- **Menu & search** — Menu, hours, search, dietary/allergen filters  
- **Cart & checkout** — Orders and carts in **PostgreSQL**  
- **RAG** — ChromaDB + embeddings  
- **Rate limiting** — SlowAPI per route  
- **API key auth** — Protected routes  
- **Session logging** — Chat duration, tools, client IP, etc.

## API

- **`GET /health`** — PostgreSQL connectivity (no API key)  
- **`POST /chat`** — `session_id`, `message`, optional `restaurant_id`  
- **`PATCH /order/status`** — Staff order updates  

## Security

- **Secrets:** `.env` gitignored; rotate leaked keys.  
- **Data:** `data/` and `sample_data/` gitignored — keep restaurant JSON only on trusted machines.  
- **Rate limiting** and **input validation** on chat and cart routes.  
