# Restaurant data (local only)

The API reads JSON from **`data/<restaurant_id>/`** (see `config.py`: `DATA_DIR`). That directory is **gitignored**—do not commit real menus, hours, or pricing.

## Layout on your machine

```text
data/
  restaurant_1/
    menu.json
    hours.json
    info.json
    specials.json
```

Use `sample_data/` only as a private backup or template folder if you like; it is also **gitignored** in this repo.

See `services/menu_services.py` for how files are loaded and the expected JSON shape.

## Multiple restaurants

Add another directory per tenant, using a safe id (`[a-zA-Z0-9_-]{1,64}`), for example:

```text
data/
  restaurant_1/
    menu.json
    ...
  downtown_brasserie/
    menu.json
    ...
```

Pass **`restaurant_id`** on API calls (or `?restaurant_id=` in the React app / widget). Defaults to **`restaurant_1`** when omitted. On startup, RAG runs **`index_all_restaurants()`** and indexes every valid folder under `data/`.
