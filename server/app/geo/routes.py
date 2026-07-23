"""Address helpers for checkout: the administrative-unit picker and
reverse geocoding.

Both exist because the MiniApp cannot do them itself. It cannot ship the
whole admin tree cheaply, so the server serves it by level; and it cannot
call a third-party geocoder (domain whitelist), so the server makes that
call on its behalf.
"""

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Query

from app.config import settings
from app.geo import store as geo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Geo"])


@router.get("/geo/provinces")
async def provinces() -> list[dict]:
    return geo.list_provinces()


@router.get("/geo/districts")
async def districts(province: Annotated[str, Query(min_length=1)]) -> list[dict]:
    return geo.list_districts(province)


@router.get("/geo/wards")
async def wards(district: Annotated[str, Query(min_length=1)]) -> list[dict]:
    return geo.list_wards(district)


@router.get("/geocode/reverse")
async def reverse_geocode(lat: float, lng: float) -> dict:
    """Coordinates to a human address, via Nominatim on the server side.

    Falls back to no address (the client keeps the coordinates and the
    manual field) if the provider is slow or unreachable, so checkout is
    never blocked by geocoding.
    """
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{settings.nominatim_base_url}/reverse",
                params={
                    "lat": lat,
                    "lon": lng,
                    "format": "json",
                    "accept-language": "vi",
                },
                # Nominatim's usage policy requires an identifying agent.
                headers={"User-Agent": "v-market-dev/1.0"},
            )
            resp.raise_for_status()
            address = resp.json().get("display_name")
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("reverse geocode failed: %s", error)
        address = None

    return {"address": address, "lat": lat, "lng": lng}
