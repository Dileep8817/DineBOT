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
