"""Placing and reading orders.

The client sends product ids and quantities — never prices. Prices come
from the database inside the same transaction that locks the stock, so
a stale or tampered cart cannot buy at yesterday's numbers.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentSeller, CurrentUser
from app.db import get_session
from app.orders import store as orders
from app.orders.store import Order, OrderError, OrderItem, ShopOrder
from app.shops import store as shops

router = APIRouter(prefix="/orders", tags=["Orders"])

Session = Annotated[AsyncSession, Depends(get_session)]


class CheckoutItem(BaseModel):
    productId: str
    # Which option was chosen. Required for a product that has options —
    # the server refuses the line otherwise rather than guessing a size.
    variantId: str | None = None
    qty: int = Field(ge=1, le=99)


class CheckoutRequest(BaseModel):
    address: str = Field(min_length=5, max_length=500)
    items: list[CheckoutItem] = Field(min_length=1, max_length=50)
    # shopId -> voucher code the buyer picked. Optional: leave it out and
    # the best applicable voucher applies itself. Re-validated server-side,
    # so a chosen code is only ever a request for a discount.
    voucherCodes: dict[str, str] | None = None


def _serialise_item(item: OrderItem) -> dict:
    return {
        "productId": item.product_id,
        "name": item.name,
        "unit": item.unit,
        "price": float(item.price),
        "qty": item.qty,
        "imageUrl": item.image_url,
        "variantId": item.variant_id,
        "variantLabel": item.variant_label,
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
        # every surcharge visible before the buyer confirms. The voucher is
        # itemised for the same reason, from the other direction.
        "shippingFee": float(shop_order.shipping_fee),
        "discount": float(shop_order.discount),
        "voucherCode": shop_order.voucher_code,
        "items": [_serialise_item(item) for item in items],
    }


def _serialise_order(order: Order, shop_views) -> dict:
    return {
        "id": order.id,
        "status": order.status,
        "address": order.address,
        "total": float(order.total),
        "createdAt": order.created_at.isoformat(),
        # When the stock this order holds goes back on sale; null once it is
        # paid or cancelled and nothing is being held.
        "expiresAt": (
            expires.isoformat()
            if (expires := orders.hold_expires_at(order)) is not None
            else None
        ),
        "shopOrders": [
            _serialise_shop_order(shop_order, shop_name, items)
            for shop_order, shop_name, items in shop_views
        ],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def place_order(
    body: CheckoutRequest, user: CurrentUser, session: Session
) -> dict:
    # Sweep first: the unit this buyer wants may be held by a checkout
    # somebody abandoned, and the hold has just run out.
    await orders.release_expired(session)

    try:
        order = await orders.place_order(
            session,
            buyer_id=user.id,
            requested=[
                (item.productId, item.variantId, item.qty)
                for item in body.items
            ],
            address=body.address,
            chosen=body.voucherCodes,
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
    # So a buyer who left an order unpaid sees it turn CANCELLED here
    # rather than finding out at the payment screen.
    await orders.release_expired(session)
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


class QuoteRequest(BaseModel):
    items: list[CheckoutItem] = Field(min_length=1, max_length=50)
    voucherCodes: dict[str, str] | None = None


# Above GET /{order_id}, like the seller routes, so "quote" isn't read as
# an order id.
@router.post("/quote")
async def quote_order(body: QuoteRequest, session: Session) -> dict:
    """Price a basket before it is placed.

    Public, like browsing: it reveals nothing a product page doesn't. The
    point is that checkout previews the *server's* arithmetic — same
    grouping, same voucher — instead of adding prices up itself and then
    disagreeing with the bill.
    """
    return await orders.quote(
        session,
        [(item.productId, item.variantId, item.qty) for item in body.items],
        chosen=body.voucherCodes,
    )


def _serialise_seller_shop_order(
    shop_order: ShopOrder, order: Order, items: list[OrderItem]
) -> dict:
    """A seller's view of one incoming slice: its own fulfilment status
    plus the parent's delivery address and date, which the seller needs to
    ship but the buyer-facing serialiser doesn't repeat per shop."""
    return {
        "id": shop_order.id,
        "orderId": order.id,
        "status": shop_order.status,
        "subtotal": float(shop_order.subtotal),
        "shippingFee": float(shop_order.shipping_fee),
        "discount": float(shop_order.discount),
        "voucherCode": shop_order.voucher_code,
        "address": order.address,
        "createdAt": order.created_at.isoformat(),
        "items": [_serialise_item(item) for item in items],
    }


async def _seller_shop_id(seller, session: Session) -> str:
    """The calling seller's shop id, or 404 — the scope every seller order
    endpoint runs inside."""
    shop = await shops.find_by_owner(session, seller.id)
    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No shop yet"
        )
    return shop.id


# These two sit above GET /{order_id} on purpose: registered first, they
# match /orders/shop before the catch-all id route can swallow "shop".
@router.get("/shop")
async def shop_incoming_orders(
    seller: CurrentSeller,
    session: Session,
    order_status: Annotated[
        Literal["CONFIRMED", "SHIPPING", "DELIVERED", "CANCELLED"] | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """The seller's fulfilment queue: their shop's slices of paid orders,
    optionally filtered to one fulfilment status."""
    shop_id = await _seller_shop_id(seller, session)
    rows = await orders.list_for_shop(
        session, shop_id, order_status, limit=limit, offset=offset
    )
    return {
        "items": [
            _serialise_seller_shop_order(shop_order, order, items)
            for shop_order, order, items in rows
        ],
        "hasMore": len(rows) == limit,
    }


class FulfilRequest(BaseModel):
    # Only forward steps a seller drives; CANCELLED would mean a refund the
    # mock gateway doesn't model, so it isn't accepted here.
    status: Literal["SHIPPING", "DELIVERED"]


@router.patch("/shop/{shop_order_id}")
async def advance_shop_order(
    shop_order_id: str,
    body: FulfilRequest,
    seller: CurrentSeller,
    session: Session,
) -> dict:
    shop_id = await _seller_shop_id(seller, session)
    shop_order, order, items, code = await orders.advance_fulfilment(
        session, shop_order_id, shop_id, body.status
    )

    if code == "NOT_FOUND":
        # 404 for both missing and not-yours — a seller cannot probe which
        # shop_order ids belong to other shops (AUTH-05).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    if code != "OK":
        messages = {
            "NOT_PAYABLE": "Order is not paid",
            "TERMINAL": "This delivery is already complete",
            "INVALID_TRANSITION": "That status change isn't allowed",
        }
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=messages.get(code, "Cannot update this order"),
        )

    return _serialise_seller_shop_order(shop_order, order, items)


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
