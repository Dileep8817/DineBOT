# Menu and restaurant data; validates restaurant_id to prevent path traversal

import json
from pathlib import Path

from config import DATA_DIR
from validation import validate_restaurant_id


class RestaurantDataNotFound(Exception):
    """Raised when menu.json (or other data file) is missing for a valid restaurant_id."""

    def __init__(self, restaurant_id: str, filename: str):
        self.restaurant_id = restaurant_id
        self.filename = filename
        super().__init__(f"No {filename} for restaurant_id={restaurant_id!r}")

def _data_path(restaurant_id: str, filename: str) -> Path:
    return DATA_DIR / restaurant_id / filename


def _read_json(restaurant_id: str, filename: str):
    # Rejects anything that is not a bare slug, so restaurant_id cannot escape DATA_DIR.
    restaurant_id = validate_restaurant_id(restaurant_id)
    path = _data_path(restaurant_id, filename)
    if not path.is_file():
        raise RestaurantDataNotFound(restaurant_id, filename)
    with path.open() as f:
        return json.load(f)


def load_menu(restaurant_id: str):
    return _read_json(restaurant_id, "menu.json")


def load_hours(restaurant_id: str):
    return _read_json(restaurant_id, "hours.json")
    
# returns the MENU data
def get_menu(restaurant_id :str):
    return load_menu(restaurant_id)

# returns the HOURS data
def get_hours(restaurant_id : str):
    return load_hours(restaurant_id)

# function that loops through all items in MENU to see if the user query is in the items of MENU or in the description of MENU 
def search_menu(restaurant_id:  str, query: str):
    menu = load_menu(restaurant_id)

    results = []
    search_term = query.lower()

    for item in menu['items']:
        name = item["name"].lower()
        description = item.get("description", "").lower()

        if search_term in name or search_term in description:
            results.append(item)
    return results

# function that loops through MENU and returns the first instance of an item; usually when a user asks for specifics on an item
def get_menu_item(restaurant_id: str, name: str):
    menu = load_menu(restaurant_id)
    search_name = name.lower()
    for item in menu['items']:
        if search_name in item['name'].lower():
            return item
    return None


def load_restaurant_info(restaurant_id: str):
    return _read_json(restaurant_id, "info.json")


def get_restaurant_info(restaurant_id: str):
    return load_restaurant_info(restaurant_id)


def load_specials(restaurant_id: str):
    return _read_json(restaurant_id, "specials.json")


def get_specials(restaurant_id: str):
    return load_specials(restaurant_id)


def filter_menu_by_dietary(restaurant_id: str, dietary_tag: str):
    """Filter menu items by dietary tag: vegetarian, vegan, gluten-free, dairy-free."""
    menu = load_menu(restaurant_id)
    tag = dietary_tag.lower().replace(" ", "-").replace("free", "free")
    if tag == "gluten-free":
        tag = "gluten"
        exclude = True
    elif tag == "dairy-free":
        tag = "dairy"
        exclude = True
    else:
        exclude = False
    results = []
    for item in menu["items"]:
        item_allergens = [a.lower() for a in item.get("allergens", [])]
        item_dietary = [d.lower() for d in item.get("dietary", [])]
        if exclude:
            if tag not in item_allergens:
                results.append(item)
        elif tag in item_dietary or tag.replace("-", " ") in item_dietary:
            results.append(item)
    return results


def get_allergen_info(restaurant_id: str, allergen: str):
    """List items that contain (or optionally avoid) an allergen."""
    menu = load_menu(restaurant_id)
    allergen_lower = allergen.lower()
    containing = [i for i in menu["items"] if allergen_lower in [a.lower() for a in i.get("allergens", [])]]
    return {"allergen": allergen, "items_containing": containing}