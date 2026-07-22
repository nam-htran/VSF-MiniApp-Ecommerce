"""Shop management.

Two rules the tests care about:
  PROD-02  one seller may own only one shop (MVP)
  AUTH-05  a seller may only touch their own shop, checked server-side
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentSeller
from app.db import get_session
from app.shops import store as shops
from app.shops.store import Shop

router = APIRouter(prefix="/shops", tags=["Shops"])

Session = Annotated[AsyncSession, Depends(get_session)]


class CreateShopRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    imageUrl: str | None = None


class UpdateShopRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    imageUrl: str | None = None


def _serialise(shop: Shop) -> dict:
    return {
        "id": shop.id,
        "ownerId": shop.owner_id,
        "name": shop.name,
        "description": shop.description,
        "imageUrl": shop.image_url,
        "status": shop.status,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_shop(
    body: CreateShopRequest, seller: CurrentSeller, session: Session
) -> dict:
    try:
        shop = await shops.create_shop(
            session,
            owner_id=seller.id,
            name=body.name,
            description=body.description,
            image_url=body.imageUrl,
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

    return _serialise(shop)


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
