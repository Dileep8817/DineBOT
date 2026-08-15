# Restaurant data

The API reads JSON from **`data/<restaurant_id>/`** (`config.py`: `DATA_DIR`, overridable with the `DATA_DIR` env var).

Two directories are involved, and they are tracked differently:

| Directory | Tracked in git? | What belongs there |
| --- | --- | --- |
| `sample_data/` | **Yes** | Fictional seed restaurants that ship with the repo |
| `data/` | **No** (gitignored) | The restaurants you actually serve: real menus, hours, pricing |

## Seeding a fresh clone

`data/` starts out empty, so seed it from the committed sample restaurant:

```bash
python -m scripts.seed_data          # copies sample_data/* into data/, skipping what exists
python -m scripts.seed_data --force  # overwrite existing folders
```

The plain copy also works:

```bash
cp -r sample_data/restaurant_1 data/restaurant_1
```

Setting `SEED_SAMPLE_DATA=1` runs the same seeder on app startup (this is what `docker compose up` uses).

## Layout

```text
data/
  restaurant_1/
    menu.json
    hours.json
    info.json
    specials.json
```

All four files are required. A missing file returns **404** naming the file, rather than a 500.

## Expected shapes

See `sample_data/restaurant_1/` for a complete working example, and `services/menu_services.py` for how each file is loaded.

- **`menu.json`** — `{"restaurant_id", "currency", "categories": [...], "items": [{"id", "name", "category", "price", "description", "dietary": [...], "allergens": [...]}]}`. `dietary` drives `filter_menu_by_dietary` (`vegetarian`, `vegan`, `gluten-free`, `dairy-free`); `allergens` drives `get_allergen_info` and the gluten-free/dairy-free exclusions.
- **`hours.json`** — a flat mapping of day name to a display string; extra keys (e.g. `Holiday_hours`) are returned as-is.
- **`info.json`** — `name`, `description`, `address`, `phone`, `email`, `policies`, `pickup_available`, `delivery_available`, `delivery_fee`, `delivery_minimum`. `services/rag_service.py` reads these keys when building the info chunk.
- **`specials.json`** — `happy_hour` (`when`, `details`), `daily_specials[]` (`day`, `title`, `description`, `discount`), `ongoing[]` (`title`, `description`, `valid`).

## Multiple restaurants

One folder per tenant, named with a safe id (`[a-zA-Z0-9_-]{1,64}`) — the pattern is enforced in `validation.py` to keep `restaurant_id` out of path traversal:

```text
data/
  restaurant_1/
  downtown_brasserie/
```

`restaurant_id` is **required** on API calls and in the React app / widget (`?restaurant_id=`); there is no default tenant. On startup, RAG runs `index_all_restaurants()`, which indexes every valid folder under `DATA_DIR` that is not already in the Chroma collection.
