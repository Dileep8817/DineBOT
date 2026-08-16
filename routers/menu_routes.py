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
from validation import (
    ITEM_NAME_MAX_LEN,
    RESTAURANT_ID_MAX_LEN,
    validate_item_name,
    validate_restaurant_id,
)

router = APIRouter(dependencies=[Depends(require_api_key)])

RestaurantId = Query(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN)


@router.get("/menu")
@limiter.limit("120/minute")
async def menu(request: Request, restaurant_id: str = RestaurantId):
    return get_menu(validate_restaurant_id(restaurant_id))


@router.get("/hours")
@limiter.limit("120/minute")
async def hours(request: Request, restaurant_id: str = RestaurantId):
    return get_hours(validate_restaurant_id(restaurant_id))


@router.get("/search-menu")
@limiter.limit("120/minute")
async def search_menu_endpoint(
    request: Request,
    restaurant_id: str = RestaurantId,
    q: str = Query(..., min_length=1, max_length=ITEM_NAME_MAX_LEN),
):
    return search_menu(validate_restaurant_id(restaurant_id), q.strip())


@router.get("/menu-item")
@limiter.limit("120/minute")
async def menu_item(
    request: Request,
    restaurant_id: str = RestaurantId,
    name: str = Query(..., min_length=1, max_length=ITEM_NAME_MAX_LEN),
):
    """Exact name, or a unique partial name. Several matches return 409 with the candidates."""
    item = get_menu_item(validate_restaurant_id(restaurant_id), validate_item_name(name))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.get("/restaurant-info")
@limiter.limit("120/minute")
async def restaurant_info(request: Request, restaurant_id: str = RestaurantId):
    return get_restaurant_info(validate_restaurant_id(restaurant_id))


@router.get("/specials")
@limiter.limit("120/minute")
async def specials(request: Request, restaurant_id: str = RestaurantId):
    return get_specials(validate_restaurant_id(restaurant_id))
