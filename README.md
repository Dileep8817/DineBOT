# DineBot

LLM-powered ordering assistant for a restaurant: customers ask about the menu, hours and dietary options in chat, build a cart, check out and pay; kitchen staff watch orders arrive on a live dashboard and advance them through the kitchen.

- **Backend** — FastAPI, PostgreSQL, OpenAI tool-calling, ChromaDB for retrieval, Stripe for payments
- **Frontend** — one React app serving three views: the ordering page, an embeddable widget, and the staff dashboard

## Quick start with Docker

Brings up PostgreSQL and the API, seeded with the sample restaurant:

```bash
cp .env.example .env       # add OPENAI_API_KEY if you want the chat to answer
docker compose up --build
```

The API is then on <http://localhost:8000>; check <http://localhost:8000/health>. The compose file defaults to `DINEBOT_DEV=1`, which accepts the public development keys (`dinebot-local-dev` for customers, `dinebot-local-staff` for staff). Set your own `API_KEY` and `STAFF_API_KEY` and `DINEBOT_DEV=0` before exposing it to anyone else.

The frontend is not containerised; run it from `react-frontend/` as below.

## Local setup

### 1. Python and PostgreSQL

```bash
pip install -r requirements.txt
createdb restaurant_ai
```

Tables are created on startup, and new columns are added with idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migrations, so an existing database upgrades in place.

### 2. Environment

Copy `.env.example` to `.env` in the project root and set `DATABASE_URL`. The backend loads that file once, in `config.py`; `npm start` and `npm run build` in `react-frontend/` read the same file through `env-cmd`, so there is one place to edit.

The minimum to boot:

```bash
DATABASE_URL=postgresql://USER@localhost:5432/restaurant_ai
DINEBOT_DEV=1
```

`DINEBOT_DEV=1` is what makes the public development keys usable. Without it the server refuses to start until `API_KEY` is set — see [Security model](#security-model). `OPENAI_API_KEY` is required for `/chat` and for retrieval; everything else (menu, cart, checkout, staff dashboard) works without it.

### 3. Restaurant data

Menus are read from `DATA_DIR` (default `data/`), one folder per restaurant, named `[A-Za-z0-9_-]{1,64}`. A fictional restaurant is committed under `sample_data/restaurant_1/`. Copy it into place:

```bash
python3 -m scripts.seed_data          # or: cp -r sample_data/restaurant_1 data/restaurant_1
```

The script skips restaurants that already exist; `--force` overwrites them. Setting `SEED_SAMPLE_DATA=1` does the same on startup, which is how the Docker stack comes up with something to serve.

Each folder holds `menu.json`, `hours.json`, `info.json` and `specials.json`; the sample files document the shapes that `services/menu_services.py` expects. Real venue data stays out of the repo — `data/` is gitignored, `sample_data/` is not. See `docs/RESTAURANT_DATA.md`.

### 4. Run the backend

From the project root, where `main.py` lives:

```bash
python3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

(Running it as a module avoids the common macOS case where `uvicorn` is not on `PATH` but is installed for that interpreter.)

### 5. Run the frontend

There is no `package.json` at the repo root; the React app lives in `react-frontend/`:

```bash
cd react-frontend && npm install && npm start
```

The browser calls same-origin `/api/*`, and the dev proxy in `src/setupProxy.js` forwards to `DINEBOT_PROXY_TARGET` and attaches `X-API-Key` server-side, so the customer key never reaches the client bundle. Keep `DINEBOT_PROXY_API_KEY` equal to `API_KEY`.

Open the ordering page with a restaurant selected — `http://localhost:3000/?restaurant_id=restaurant_1` — or set `REACT_APP_DEFAULT_RESTAURANT_ID`. Without either, the app says so rather than silently calling the API with no tenant.

## Views

| Path | View |
| --- | --- |
| `/` | Customer ordering page |
| `/widget` (or `?embed=1`) | Embeddable widget, for an iframe on the restaurant's own site |
| `/staff` | Kitchen dashboard |

The widget accepts `restaurant_id`, `restaurant_name` and `primary_color` as query parameters:

```html
<iframe src="https://your-frontend/widget?restaurant_id=restaurant_1" width="420" height="640"></iframe>
```

## Staff dashboard

`/staff` asks for a staff key, stores it in `localStorage`, and sends it as `X-Staff-Key` — never in the URL. It shows three columns (New, Preparing, Ready) with each order's items, total and payment status, and one button per card to advance it.

Updates arrive over Server-Sent Events from `GET /staff/stream`, which polls `orders.updated_at` and emits new and changed orders. Polling rather than in-process pub/sub means it still works with several uvicorn workers; `STAFF_STREAM_POLL_SECONDS` (default 2) sets the interval. The client reconnects with backoff and re-syncs from a snapshot.

Status changes go through the same state machine as everything else:

```
pending → preparing → ready → completed
   ↓          ↓
cancelled  cancelled
```

Anything else is refused with 409 and the list of allowed next statuses. `completed` and `cancelled` are terminal. The transition is applied under `SELECT ... FOR UPDATE`, so two staff clicking at once cannot double-advance an order.

## Security model

**Two separate secrets.** The customer key (`X-API-Key`) is handed to every browser that loads the ordering widget, so it authorises only session-scoped customer actions. Staff endpoints require a different key in a different header (`X-Staff-Key`, from `STAFF_API_KEY`). Configuring the same value for both stops startup.

**No usable default.** The keys `dinebot-local-dev` and `dinebot-local-staff` are committed to this repository, so they authenticate nobody. They are accepted only when `DINEBOT_DEV=1` is set explicitly. With no key configured and no dev flag, startup fails with an explanatory error instead of serving traffic; putting either key in `API_KEY` without the flag is refused too.

**Customers see only their own orders.** `GET /order/status` and the equivalent chat tool require `session_id` and scope the lookup to it, so the predictable order numbers (`RESTAURANT_1-0007`) cannot be walked. Reading any order of a restaurant is a separate, staff-authorised code path (`get_order_for_staff`), and customers cannot change an order's status at all — that route is staff-only.

**Input validation** lives in one place, `validation.py`: session and restaurant id patterns, length caps and quantity bounds. `restaurant_id` becomes a path segment under `DATA_DIR`, so its pattern is what prevents traversal. Quantities are bounded 1–99 in the service layer, not only in the routes, because the LLM tool path does not go through FastAPI's query validation.

**Ambiguous item names are refused, not guessed.** `get_menu_item` matches exactly (case-insensitively) first, then a substring only if it is unique; two candidates give 409 with both names. A customer is never charged for an item they did not name.

**CORS** is off unless `ALLOWED_ORIGINS` lists origins, which is correct when the SPA and API share a hostname. `*` is refused unless `DINEBOT_DEV=1`.

Also: rate limiting per route via SlowAPI, keys compared with `secrets.compare_digest`, and Stripe webhooks verified against `STRIPE_WEBHOOK_SECRET` (`/payments/webhook` answers 503 if it is unset).

## API

Public: `GET /`, `GET /health` (reports PostgreSQL connectivity).

Customer routes, all requiring `X-API-Key` and a `restaurant_id`:

| Route | Purpose |
| --- | --- |
| `GET /menu`, `/hours`, `/specials`, `/restaurant-info` | Restaurant data |
| `GET /search-menu`, `/menu-item` | Search; resolve one item by name |
| `GET /cart`, `/cart/summary` | Read the session's cart |
| `POST /cart/add`, `/cart/update`, `/cart/remove`, `/cart/clear` | Modify it |
| `POST /order/checkout` | Turn the cart into an order |
| `GET /order/status` | The session's own order only |
| `POST /chat` | `session_id`, `message`, `restaurant_id` |
| `POST /payments/create-intent` | Stripe intent for an order the session owns |

Staff routes, all requiring `X-Staff-Key`:

| Route | Purpose |
| --- | --- |
| `GET /staff/session` | Validate the key; returns the status flow |
| `GET /staff/orders` | The restaurant's orders, optionally filtered by status |
| `GET /staff/orders/{order_number}` | One order |
| `PATCH /staff/orders/{order_number}/status` | Advance it |
| `GET /staff/stream` | SSE stream of new and changed orders |

`POST /payments/webhook` is called by Stripe and authenticated by signature, not by an API key.

## Payments

Set `STRIPE_SECRET_KEY` and `REACT_APP_STRIPE_PUBLISHABLE_KEY` to enable the Payment Element at checkout. `POST /payments/create-intent` verifies the order belongs to the requesting session, then moves `payment_status` from `unpaid` to `processing`. The webhook settles it: `paid` on success, `failed` on a decline, back to `unpaid` if the intent is cancelled. Only `paid` blocks a retry. Locally:

```bash
stripe listen --forward-to localhost:8000/payments/webhook
```

and put the printed signing secret in `STRIPE_WEBHOOK_SECRET`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite needs a reachable PostgreSQL: it derives a `*_test` database from `DATABASE_URL` (or uses `TEST_DATABASE_URL`), creates it, and truncates tables between tests. It skips itself if no server is reachable. It reads menus from `sample_data/`, and stubs Stripe and the LLM, so no test makes a network call.

Coverage is deliberately concentrated on the parts where a bug is expensive: cart arithmetic and isolation, the order and payment state machines, menu name resolution, and regressions for each security fix above (`tests/test_security_regressions.py`).

The frontend has its own tests, including the staff dashboard rendering against a mocked SSE stream:

```bash
cd react-frontend && CI=true npm test
```

## Deployment notes

Prefer one hostname: serve the SPA and route `/api/*` to FastAPI (nginx `proxy_pass`, stripping `/api` like the dev proxy does), attaching `X-API-Key` upstream so the browser never sees it. Then no CORS configuration is needed. If the API is on its own origin, set `ALLOWED_ORIGINS` to the exact SPA origins and `REACT_APP_API_BASE` to the API base.

Set `DINEBOT_DEV=0` (or leave it unset), generate `API_KEY` and `STAFF_API_KEY`, and terminate TLS in front of the API. RAG indexing runs at startup and skips restaurants already in Chroma; set `RAG_INDEX_ON_STARTUP=0` to run it as a separate job instead, or `RAG_REINDEX=1` after changing a menu.

`.env.example` lists every variable the code reads, with defaults.
