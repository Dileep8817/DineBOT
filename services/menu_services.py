# Menu and restaurant data; validates restaurant_id to prevent path traversal

import json
import re

from config import DATA_DIR

RESTAURANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# safety protection protocal
def _validate_restaurant_id(restaurant_id: str) -> None:
    if not restaurant_id or not RESTAURANT_ID_PATTERN.match(restaurant_id):
        raise ValueError("restaurant_id must be 1-64 chars: letters, numbers, underscore, hyphen only")


def _data_path(restaurant_id: str, filename: str) -> str:
    return str(DATA_DIR / restaurant_id / filename)


def load_menu(restaurant_id: str):
    _validate_restaurant_id(restaurant_id)
    with open(_data_path(restaurant_id, "menu.json")) as f:
        return json.load(f)


def load_hours(restaurant_id: str):
    _validate_restaurant_id(restaurant_id)
    with open(_data_path(restaurant_id, "hours.json")) as f:
        return json.load(f)
    
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
    _validate_restaurant_id(restaurant_id)
    with open(_data_path(restaurant_id, "info.json")) as f:
        return json.load(f)


def get_restaurant_info(restaurant_id: str):
    return load_restaurant_info(restaurant_id)


def load_specials(restaurant_id: str):
    _validate_restaurant_id(restaurant_id)
    with open(_data_path(restaurant_id, "specials.json")) as f:
        return json.load(f)


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