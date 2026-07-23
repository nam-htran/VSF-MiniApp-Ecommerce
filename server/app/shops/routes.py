"""Shop management.

Three rules the tests care about:
  PROD-02  one seller may own only one shop (MVP)
  AUTH-04  a user with no shop cannot reach the seller endpoints
  AUTH-05  a seller may only touch their own shop, checked server-side

Opening a shop is open to any logged-in user — that action is what turns a
buyer into a seller. Requiring the SELLER role to create a shop would mean
nobody could ever become one.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentSeller, CurrentUser
from app.db import get_session
from app.shops import store as shops
from app.shops.store import Shop
from app.users import store as users

router = APIRouter(prefix="/shops", tags=["Shops"])

Session = Annotated[AsyncSession, Depends(get_session)]


class CreateShopRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    imageUrl: str | None = None
    logoUrl: str | None = None
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=20)
    province: str | None = Field(default=None, max_length=120)


class UpdateShopRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    imageUrl: str | None = None
    logoUrl: str | None = None
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=20)
    province: str | None = Field(default=None, max_length=120)


def _serialise(shop: Shop) -> dict:
    return {
        "id": shop.id,
        "ownerId": shop.owner_id,
        "name": shop.name,
        "description": shop.description,
        "imageUrl": shop.image_url,
        "logoUrl": shop.logo_url,
        "address": shop.address,
        "phone": shop.phone,
        "province": shop.province,
        "status": shop.status,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_shop(
    body: CreateShopRequest, user: CurrentUser, session: Session
) -> dict:
    try:
        shop = await shops.create_shop(
            session,
            owner_id=user.id,
            name=body.name,
            description=body.description,
            image_url=body.imageUrl,
            logo_url=body.logoUrl,
            address=body.address,
            phone=body.phone,
            province=body.province,
        )
    except IntegrityError:
        # The unique index on owner_id rejected a second shop. Catching the
        # constraint rather than pre-checking closes the race between two
        # concurrent creates.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This seller already has a shop",
        ) from None

    # Same person, same account — they just gained a shop and keep buying
    # from others.
    await users.promote_to_seller(session, user)
    return _serialise(shop)


@router.get("")
async def list_shops(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Public: the buyer home screen, which must work without login."""
    shops_page = await shops.list_active(session, limit=limit, offset=offset)
    return {
        "items": [_serialise(shop) for shop in shops_page],
        # No total count: it costs a second query and the home screen only
        # needs to know whether to keep scrolling.
        "hasMore": len(shops_page) == limit,
    }


@router.get("/me")
async def get_my_shop(seller: CurrentSeller, session: Session) -> dict:
    shop = await shops.find_by_owner(session, seller.id)
    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No shop yet"
        )
    return _serialise(shop)


@router.patch("/{shop_id}")
async def update_shop(
    shop_id: str,
    body: UpdateShopRequest,
    seller: CurrentSeller,
    session: Session,
) -> dict:
    shop = await shops.find_by_id(session, shop_id)

    # 404 for both "missing" and "someone else's", so the response cannot be
    # used to discover which shop ids exist.
    if shop is None or shop.owner_id != seller.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found"
        )

    updated = await shops.update_shop(
        session,
        shop,
        name=body.name,
        description=body.description,
        image_url=body.imageUrl,
        logo_url=body.logoUrl,
        address=body.address,
        phone=body.phone,
        province=body.province,
    )
    return _serialise(updated)


@router.get("/{shop_id}")
async def get_shop(shop_id: str, session: Session) -> dict:
    """Public: buyers browse shops without logging in."""
    shop = await shops.find_by_id(session, shop_id)
    if shop is None or shop.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found"
        )
    return _serialise(shop)
