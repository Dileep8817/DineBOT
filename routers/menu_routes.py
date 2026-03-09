# this file has the menu routes that the main file can pick up from

from fastapi import APIRouter, Query, HTTPException
from services.menu_services import get_menu, get_hours, search_menu, get_menu_item, get_restaurant_info, get_specials

router = APIRouter()

@router.get("/menu")
async def menu(restaurant_id: str = Query("restaurant_1", min_length=1, max_length=64)):
    return get_menu(restaurant_id)

@router.get("/hours")
async def hours():
    return get_hours("restaurant_1")

@router.get("/search-menu")
async def search_menu_endpoint(
    restaurant_id: str = Query(...),
    q: str = Query(...)
    ):
    return search_menu(restaurant_id, q)

@router.get("/menu-item")
async def menu_item(
    restaurant_id: str = Query(...),
    name: str = Query(...)
):
    item = get_menu_item(restaurant_id, name)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.get("/restaurant-info")
async def restaurant_info(restaurant_id: str = Query("restaurant_1")):
    return get_restaurant_info(restaurant_id)


@router.get("/specials")
async def specials(restaurant_id: str = Query("restaurant_1")):
    return get_specials(restaurant_id)