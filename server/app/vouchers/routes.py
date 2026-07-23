"""Vouchers: public listing for the promo strip, seller CRUD for their own.

Nobody types a code — the best applicable one applies itself, on the card
and again on the order. These endpoints exist so the promo strip can show
what is running and so a seller can run a sale.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentSeller
from app.db import get_session
from app.shops import store as shops
from app.vouchers import store as vouchers
from app.vouchers.store import Voucher

router = APIRouter(prefix="/vouchers", tags=["Vouchers"])

Session = Annotated[AsyncSession, Depends(get_session)]


class CreateVoucherRequest(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    description: str = Field(min_length=1, max_length=200)
    # A category key (products.category); omit for "everything I sell".
    category: str | None = Field(default=None, max_length=40)
    discountType: Literal["PERCENT", "AMOUNT"]
    discountValue: Decimal = Field(gt=0)
    maxDiscount: Decimal | None = Field(default=None, gt=0)
    minOrder: Decimal = Field(default=Decimal("0"), ge=0)
    startsAt: datetime
    endsAt: datetime


def _serialise(voucher: Voucher) -> dict:
    return {
        "id": voucher.id,
        "code": voucher.code,
        "description": voucher.description,
        "shopId": voucher.shop_id,
        "category": voucher.category,
        "discountType": voucher.discount_type,
        "discountValue": float(voucher.discount_value),
        "maxDiscount": (
            float(voucher.max_discount) if voucher.max_discount is not None else None
        ),
        "minOrder": float(voucher.min_order),
        "startsAt": voucher.starts_at.isoformat(),
        "endsAt": voucher.ends_at.isoformat(),
        "status": voucher.status,
    }


@router.get("")
async def list_vouchers(
    session: Session,
    shopId: Annotated[str | None, Query()] = None,
) -> dict:
    """Public: what is running right now. Expired vouchers simply stop
    coming back — the promo strip needs no cleanup job."""
    live = await vouchers.list_live(session, shop_id=shopId)
    return {"items": [_serialise(voucher) for voucher in live]}


@router.get("/mine")
async def my_vouchers(seller: CurrentSeller, session: Session) -> dict:
    """The seller's own, expired ones included — they manage the list."""
    shop = await shops.find_by_owner(session, seller.id)
    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No shop yet"
        )
    owned = await vouchers.list_for_shop(session, shop.id)
    return {"items": [_serialise(voucher) for voucher in owned]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_voucher(
    body: CreateVoucherRequest, seller: CurrentSeller, session: Session
) -> dict:
    shop = await shops.find_by_owner(session, seller.id)
    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No shop yet"
        )

    if body.endsAt <= body.startsAt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The voucher must end after it starts",
        )
    if body.discountType == "PERCENT" and body.discountValue > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A percentage cannot exceed 100",
        )

    try:
        created = await vouchers.create_voucher(
            session,
            code=body.code,
            description=body.description,
            # A seller may only ever cut their own prices, never the
            # marketplace's — platform-wide vouchers are seeded, not posted.
            shop_id=shop.id,
            category=body.category,
            discount_type=body.discountType,
            discount_value=body.discountValue,
            max_discount=body.maxDiscount,
            min_order=body.minOrder,
            starts_at=body.startsAt,
            ends_at=body.endsAt,
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That code is already taken",
        ) from None

    return _serialise(created)


@router.patch("/{voucher_id}/status")
async def set_voucher_status(
    voucher_id: str,
    body: dict,
    seller: CurrentSeller,
    session: Session,
) -> dict:
    """Stop or restart a sale without deleting its history."""
    new_status = body.get("status")
    if new_status not in ("ACTIVE", "DISABLED"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be ACTIVE or DISABLED",
        )

    shop = await shops.find_by_owner(session, seller.id)
    voucher = await vouchers.find_by_id(session, voucher_id)
    # 404 for missing and for someone else's alike, as everywhere else.
    if voucher is None or shop is None or voucher.shop_id != shop.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Voucher not found"
        )

    return _serialise(await vouchers.set_status(session, voucher, new_status))
