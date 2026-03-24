# Restaurant AI Agent

LLM-powered chatbot for restaurants: take orders, answer questions about the menu, hours, and more.

## Setup

### 1. Python

```bash
pip install -r requirements.txt
```

### 2. Environment and secrets

Copy `.env.example` to `.env` and set values **locally**. Never commit `.env` or paste API keys into tracked files.

- **OpenAI:** set `OPENAI_API_KEY` for `/chat` and optional RAG embeddings.
- **Database:** omit `DATABASE_URL` to use local **SQLite** (`dinebot.db`), or set a PostgreSQL URL. If PostgreSQL is unreachable, the server can fall back to SQLite (see `.env.example`).

### 3. Restaurant data (menu, hours, info, specials)

Real venue data lives under `data/<restaurant_id>/` and is **gitignored** so it is not pushed to GitHub.

After cloning, copy the sample once:

```bash
mkdir -p data && cp -R sample_data/restaurant_1 data/
```

Then edit `data/restaurant_1/*.json` with your real menu and information. The sample files are placeholders only.

### 4. PostgreSQL (optional)

If you use Postgres instead of SQLite, create a database and set `DATABASE_URL`:

```bash
createdb restaurant_ai
export DATABASE_URL=postgresql://YOUR_USER@localhost:5432/restaurant_ai
```

Tables (`cart_items`, `orders`, `order_items`) are created automatically on first run.

### 5. Run backend

```bash
uvicorn main:app --reload
```

### 6. Run frontend

```bash
cd react-frontend && npm install && npm start
```

### 7. DineBot logo (widget)

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

Cart and order data are stored in **PostgreSQL** (if configured) or **SQLite** locally.

## API

- **Health:** `GET /health` returns `{"status":"ok","database":"connected"}` or 503 if DB is down.
- **Chat** accepts optional `restaurant_id` in the body (default `restaurant_1`). All tools are scoped by it.
- **Order status (staff):** `PATCH /order/status?order_number=RESTAURANT_1-0001&status=preparing` to update status (`pending`, `preparing`, `ready`, `completed`, `cancelled`).

## Production

- Set **CORS_ORIGINS** (comma-separated) in `.env` for your frontend and embed domains.
- In **react-frontend**, set **REACT_APP_API_BASE** to your API URL (e.g. `https://api.yourdomain.com`).
- Chat requests are logged (restaurant_id, session_id, message length) for debugging and analytics.

## Security

- **Secrets:** Keep `.env` out of version control; rotate any API key that was ever committed or shared.
- **Restaurant data:** The `data/` directory is ignored by git; use `sample_data/` as a template only.
- **Rate limiting:** `POST /chat` is limited to 30 requests/minute per IP (SlowAPI).
- **Input validation:** Chat message length (1–2000 chars), session_id format, cart quantity (1–99), and `restaurant_id` (path traversal prevented).
- **Optional API key:** Set `API_KEY` or `API_KEYS` in `.env` and use `Depends(verify_api_key)` on admin routes (see `auth.py`).
