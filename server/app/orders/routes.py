"""Placing and reading orders.

The client sends product ids and quantities — never prices. Prices come
from the database inside the same transaction that locks the stock, so
a stale or tampered cart cannot buy at yesterday's numbers.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.db import get_session
from app.orders import store as orders
from app.orders.store import Order, OrderError, OrderItem, ShopOrder

router = APIRouter(prefix="/orders", tags=["Orders"])

Session = Annotated[AsyncSession, Depends(get_session)]


class CheckoutItem(BaseModel):
    productId: str
    qty: int = Field(ge=1, le=99)


class CheckoutRequest(BaseModel):
    address: str = Field(min_length=5, max_length=500)
    items: list[CheckoutItem] = Field(min_length=1, max_length=50)


def _serialise_item(item: OrderItem) -> dict:
    return {
        "productId": item.product_id,
        "name": item.name,
        "unit": item.unit,
        "price": float(item.price),
        "qty": item.qty,
        "imageUrl": item.image_url,
    }


def _serialise_shop_order(
    shop_order: ShopOrder, shop_name: str, items: list[OrderItem]
) -> dict:
    return {
        "id": shop_order.id,
        "shopId": shop_order.shop_id,
        "shopName": shop_name,
        "status": shop_order.status,
        "subtotal": float(shop_order.subtotal),
        # Itemised, not folded into the total — review rule 5.2.1 wants
        # every surcharge visible before the buyer confirms.
        "shippingFee": float(shop_order.shipping_fee),
        "items": [_serialise_item(item) for item in items],
    }


def _serialise_order(order: Order, shop_views) -> dict:
    return {
        "id": order.id,
        "status": order.status,
        "address": order.address,
        "total": float(order.total),
        "createdAt": order.created_at.isoformat(),
        "shopOrders": [
            _serialise_shop_order(shop_order, shop_name, items)
            for shop_order, shop_name, items in shop_views
        ],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def place_order(
    body: CheckoutRequest, user: CurrentUser, session: Session
) -> dict:
    try:
        order = await orders.place_order(
            session,
            buyer_id=user.id,
            requested=[(item.productId, item.qty) for item in body.items],
            address=body.address,
        )
    except OrderError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=error.message
        ) from None

    view = await orders.shop_orders_view(session, [order.id])
    return _serialise_order(order, view.get(order.id, []))


@router.get("")
async def my_orders(
    user: CurrentUser,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    page = await orders.list_for_buyer(
        session, user.id, limit=limit, offset=offset
    )
    view = await orders.shop_orders_view(session, [order.id for order in page])
    return {
        "items": [
            _serialise_order(order, view.get(order.id, [])) for order in page
        ],
        "hasMore": len(page) == limit,
    }


@router.get("/{order_id}")
async def get_order(order_id: str, user: CurrentUser, session: Session) -> dict:
    order = await orders.find_by_id(session, order_id)

    # 404 for both "missing" and "someone else's", as everywhere else —
    # the response must not reveal which order ids exist.
    if order is None or order.buyer_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )

    view = await orders.shop_orders_view(session, [order.id])
    return _serialise_order(order, view.get(order.id, []))
