# Menu and restaurant read routes (API key + rate limit)

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_api_key
from config import limiter
from services.menu_services import (
    get_menu,
    get_hours,
    search_menu,
    get_menu_item,
    get_restaurant_info,
    get_specials,
)

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/menu")
@limiter.limit("120/minute")
async def menu(
    request: Request,
    restaurant_id: str = Query("restaurant_1", min_length=1, max_length=64),
):
    return get_menu(restaurant_id)


@router.get("/hours")
@limiter.limit("120/minute")
async def hours(
    request: Request,
    restaurant_id: str = Query("restaurant_1", min_length=1, max_length=64),
):
    return get_hours(restaurant_id)


@router.get("/search-menu")
@limiter.limit("120/minute")
async def search_menu_endpoint(
    request: Request,
    restaurant_id: str = Query("restaurant_1", min_length=1, max_length=64),
    q: str = Query(...),
):
    return search_menu(restaurant_id, q)


@router.get("/menu-item")
@limiter.limit("120/minute")
async def menu_item(
    request: Request,
    restaurant_id: str = Query("restaurant_1", min_length=1, max_length=64),
    name: str = Query(...),
):
    item = get_menu_item(restaurant_id, name)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.get("/restaurant-info")
@limiter.limit("120/minute")
async def restaurant_info(
    request: Request,
    restaurant_id: str = Query("restaurant_1", min_length=1, max_length=64),
):
    return get_restaurant_info(restaurant_id)


@router.get("/specials")
@limiter.limit("120/minute")
async def specials(
    request: Request,
    restaurant_id: str = Query("restaurant_1", min_length=1, max_length=64),
):
    return get_specials(restaurant_id)
