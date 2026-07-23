"""Orders, model B: one payment, many deliveries.

    orders          ← paid once, by one buyer
    └── shop_orders ← fulfilment lives here, one row per shop
        └── order_items

order_items hang off shop_orders, not orders — that split is what makes
this model B. Items snapshot name/unit/price at purchase time: a seller
changing a price tomorrow must not rewrite yesterday's receipts.

Placing an order is where INV-05 is finally enforced for real: stock
rows are locked with SELECT ... FOR UPDATE before being decremented, so
two buyers racing for the last unit cannot both win. The CHECK
constraint on products.stock stays as the last line of defence.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.products.store import Product
from app.shops.store import Shop

OrderStatus = Literal["PENDING", "PAID", "FAILED", "CANCELLED"]
ShopOrderStatus = Literal["CONFIRMED", "SHIPPING", "DELIVERED", "CANCELLED"]

# Flat per-shop fee for now. It exists so the checkout screen can honour
# review rule 5.2.1 — every surcharge itemised before confirming — and
# becomes real logistics pricing later.
SHIPPING_FEE_PER_SHOP = Decimal("15000")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(primary_key=True)
    buyer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # Payment state. Fulfilment state lives on each shop_order — a shop
    # cancelling its part must not touch payment or the other shops.
    status: Mapped[str] = mapped_column(default="PENDING")
    address: Mapped[str]
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ShopOrder(Base):
    __tablename__ = "shop_orders"

    id: Mapped[str] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), index=True)
    status: Mapped[str] = mapped_column(default="CONFIRMED")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    shipping_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_order_items_qty_positive"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    shop_order_id: Mapped[str] = mapped_column(
        ForeignKey("shop_orders.id"), index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    # Snapshot at purchase. A receipt is a photograph, not a window.
    name: Mapped[str]
    unit: Mapped[str | None]
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    qty: Mapped[int]
    image_url: Mapped[str | None]


class OrderError(Exception):
    """Domain failure the route turns into an HTTP status."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


async def place_order(
    session: AsyncSession,
    buyer_id: str,
    requested: list[tuple[str, int]],
    address: str,
) -> Order:
    """One transaction: lock stock, split by shop, snapshot prices.

    All-or-nothing on purpose — an order that silently drops the
    out-of-stock half would ship something different from what the buyer
    confirmed.
    """
    # Merge duplicate lines before locking.
    wanted: dict[str, int] = {}
    for product_id, qty in requested:
        wanted[product_id] = wanted.get(product_id, 0) + qty

    # Lock rows in a stable order. Two checkouts locking {A,B} and {B,A}
    # would deadlock; both locking in sorted order cannot.
    products: dict[str, Product] = {}
    for product_id in sorted(wanted):
        product = await session.get(Product, product_id, with_for_update=True)
        if product is None or product.status != "ACTIVE":
            raise OrderError("UNAVAILABLE", "Product is no longer available")
        products[product_id] = product

    short = [
        product.name
        for product_id, product in products.items()
        if product.stock < wanted[product_id]
    ]
    if short:
        raise OrderError(
            "OUT_OF_STOCK", f"Not enough stock for: {', '.join(sorted(short))}"
        )

    for product_id, product in products.items():
        product.stock -= wanted[product_id]

    by_shop: dict[str, list[str]] = {}
    for product_id, product in products.items():
        by_shop.setdefault(product.shop_id, []).append(product_id)

    order = Order(
        id=str(uuid.uuid4()),
        buyer_id=buyer_id,
        address=address,
        total=Decimal("0"),
    )
    session.add(order)
    # Explicit flushes between the levels: these models carry no
    # relationship(), and without one the unit of work does NOT order
    # inserts by foreign key — it would happily write order_items before
    # shop_orders and hit the constraint. Flushing per level pins the
    # order; it all stays one transaction until the commit below.
    await session.flush()

    total = Decimal("0")
    shop_orders: list[ShopOrder] = []
    for shop_id in sorted(by_shop):
        subtotal = sum(
            (products[pid].price * wanted[pid] for pid in by_shop[shop_id]),
            Decimal("0"),
        )
        shop_order = ShopOrder(
            id=str(uuid.uuid4()),
            order_id=order.id,
            shop_id=shop_id,
            subtotal=subtotal,
            shipping_fee=SHIPPING_FEE_PER_SHOP,
        )
        session.add(shop_order)
        shop_orders.append(shop_order)
        total += subtotal + SHIPPING_FEE_PER_SHOP
    await session.flush()

    for shop_order in shop_orders:
        for pid in by_shop[shop_order.shop_id]:
            product = products[pid]
            session.add(
                OrderItem(
                    id=str(uuid.uuid4()),
                    shop_order_id=shop_order.id,
                    product_id=pid,
                    name=product.name,
                    unit=product.unit,
                    price=product.price,
                    qty=wanted[pid],
                    image_url=product.image_url,
                )
            )

    order.total = total
    # One commit releases the locks and makes the whole order visible —
    # or nothing at all.
    await session.commit()
    await session.refresh(order)
    return order


async def find_by_id(session: AsyncSession, order_id: str) -> Order | None:
    return await session.get(Order, order_id)


async def mark_paid(
    session: AsyncSession, order_id: str, amount: Decimal
) -> tuple[Order | None, str]:
    """Move an order PENDING → PAID on a verified payment notification.

    Idempotent: a repeated IPN for an already-paid order is a success, not
    an error — the gateway retries until it gets a 200, so the same
    notification can arrive more than once. The amount is checked against
    the order's own total so a tampered notification can't pay less than
    what was owed.
    """
    order = await session.get(Order, order_id, with_for_update=True)
    if order is None:
        return None, "NOT_FOUND"
    if order.total != amount:
        return order, "AMOUNT_MISMATCH"
    if order.status == "PAID":
        return order, "ALREADY_PAID"
    if order.status != "PENDING":
        return order, "NOT_PAYABLE"
    order.status = "PAID"
    await session.commit()
    await session.refresh(order)
    return order, "PAID"


async def list_for_buyer(
    session: AsyncSession, buyer_id: str, limit: int, offset: int
) -> list[Order]:
    rows = await session.scalars(
        select(Order)
        .where(Order.buyer_id == buyer_id)
        .order_by(Order.created_at.desc(), Order.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows)


# The forward-only fulfilment ladder a seller may walk a shop order up.
# CANCELLED is deliberately absent: a cancel after payment means a refund,
# which the mock gateway doesn't model yet, so it isn't offered.
_FULFILMENT_NEXT: dict[str, str] = {
    "CONFIRMED": "SHIPPING",
    "SHIPPING": "DELIVERED",
}


async def _items_for_shop_orders(
    session: AsyncSession, shop_order_ids: list[str]
) -> dict[str, list[OrderItem]]:
    if not shop_order_ids:
        return {}
    rows = await session.scalars(
        select(OrderItem).where(OrderItem.shop_order_id.in_(shop_order_ids))
    )
    grouped: dict[str, list[OrderItem]] = {}
    for item in rows:
        grouped.setdefault(item.shop_order_id, []).append(item)
    return grouped


async def list_for_shop(
    session: AsyncSession,
    shop_id: str,
    status_filter: str | None,
    limit: int,
    offset: int,
) -> list[tuple[ShopOrder, Order, list[OrderItem]]]:
    """A seller's incoming work: their shop's slices of PAID orders.

    Only PAID parents show — a seller has nothing to fulfil until the
    buyer has actually paid. Each row carries its parent order (for the
    delivery address and date the seller needs) and its items.
    """
    conditions = [ShopOrder.shop_id == shop_id, Order.status == "PAID"]
    if status_filter is not None:
        conditions.append(ShopOrder.status == status_filter)

    rows = (
        await session.execute(
            select(ShopOrder, Order)
            .join(Order, Order.id == ShopOrder.order_id)
            .where(*conditions)
            .order_by(Order.created_at.desc(), ShopOrder.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    items_by = await _items_for_shop_orders(session, [so.id for so, _ in rows])
    return [(so, order, items_by.get(so.id, [])) for so, order in rows]


async def advance_fulfilment(
    session: AsyncSession, shop_order_id: str, shop_id: str, target: str
) -> tuple[ShopOrder | None, Order | None, list[OrderItem], str]:
    """Walk one shop's slice one step forward, scoped to its owner.

    shop_id pins it to the calling seller's shop (AUTH-05); only the one
    legal next step is accepted, so a double-tap or a stale button can't
    skip a stage or move it backwards. Returns (shop_order, order, items,
    code).
    """
    shop_order = await session.get(
        ShopOrder, shop_order_id, with_for_update=True
    )
    if shop_order is None or shop_order.shop_id != shop_id:
        return None, None, [], "NOT_FOUND"

    order = await session.get(Order, shop_order.order_id)
    if order is None or order.status != "PAID":
        # Nothing to fulfil on an unpaid (or vanished) order.
        return shop_order, order, [], "NOT_PAYABLE"

    expected = _FULFILMENT_NEXT.get(shop_order.status)
    if expected is None:
        return shop_order, order, [], "TERMINAL"
    if target != expected:
        return shop_order, order, [], "INVALID_TRANSITION"

    shop_order.status = target
    await session.commit()
    await session.refresh(shop_order)

    items = (await _items_for_shop_orders(session, [shop_order.id])).get(
        shop_order.id, []
    )
    return shop_order, order, items, "OK"


async def shop_orders_view(
    session: AsyncSession, order_ids: list[str]
) -> dict[str, list[tuple[ShopOrder, str, list[OrderItem]]]]:
    """Children of the given orders, grouped per order, shop name joined
    in — explicit queries rather than lazy relationships, which throw
    MissingGreenlet under async."""
    if not order_ids:
        return {}

    shop_rows = (
        await session.execute(
            select(ShopOrder, Shop.name)
            .join(Shop, Shop.id == ShopOrder.shop_id)
            .where(ShopOrder.order_id.in_(order_ids))
        )
    ).all()

    item_rows = list(
        await session.scalars(
            select(OrderItem).where(
                OrderItem.shop_order_id.in_([so.id for so, _ in shop_rows])
            )
        )
    )
    items_by_shop_order: dict[str, list[OrderItem]] = {}
    for item in item_rows:
        items_by_shop_order.setdefault(item.shop_order_id, []).append(item)

    view: dict[str, list[tuple[ShopOrder, str, list[OrderItem]]]] = {}
    for shop_order, shop_name in shop_rows:
        view.setdefault(shop_order.order_id, []).append(
            (shop_order, shop_name, items_by_shop_order.get(shop_order.id, []))
        )
    return view
