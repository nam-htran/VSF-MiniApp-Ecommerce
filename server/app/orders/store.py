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
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    UniqueConstraint,
    func,
    select,
    text,
)
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
    __table_args__ = (
        # One key, one order — per buyer, so two people cannot collide on a
        # guessable key. NULLs are distinct in Postgres, so orders placed
        # without a key are unaffected. This constraint is the idempotency:
        # a retry loses the race and is handed the first order back.
        UniqueConstraint(
            "buyer_id", "idempotency_key", name="uq_orders_buyer_idempotency"
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    buyer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # Sent by the client, one per checkout attempt. Replaying the same key
    # returns the order already created rather than making a second one.
    idempotency_key: Mapped[str | None] = mapped_column(default=None)
    # The gateway session this order is being paid through, opened via our
    # own server so we know one exists. Without it the expiry sweep cannot
    # tell "abandoned basket" from "buyer is at the bank right now" — and
    # cancelling the second takes the money while giving the stock away.
    payment_id: Mapped[str | None] = mapped_column(default=None)
    payment_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
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
    # What a voucher took off this shop's slice, and which one — snapshotted
    # like the prices above, so a voucher edited or expired tomorrow leaves
    # yesterday's receipt intact.
    discount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, server_default="0"
    )
    voucher_code: Mapped[str | None] = mapped_column(default=None)


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
    # Which option was bought, and what it was called at the time. The id is
    # for the seller's own reporting; the label is what the receipt shows,
    # snapshotted because the option may be renamed or removed later.
    variant_id: Mapped[str | None] = mapped_column(default=None)
    variant_label: Mapped[str | None] = mapped_column(default=None)


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
    chosen: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> Order:
    """One transaction: lock stock, split by shop, snapshot prices.

    All-or-nothing on purpose — an order that silently drops the
    out-of-stock half would ship something different from what the buyer
    confirmed.
    """
    # A replay of a checkout the buyer already completed — the tap that
    # double-fired, the retry after a flaky connection — must return the
    # order that exists, not charge them twice. Checked before any stock is
    # touched; the unique constraint below is what settles a true race.
    if idempotency_key:
        # Take a lock on the key itself before looking. Without it both
        # copies of a double-tap read "no order yet", both do the work, and
        # the loser only discovers the clash when its INSERT trips the
        # unique constraint — deep inside a transaction that has already
        # locked stock rows. Recovering from there proved worse than
        # avoiding it: the failed flush left the pooled connection in a
        # state that made the *next* request fail too.
        #
        # Advisory locks are released when the transaction ends, so the
        # second request simply waits for the first to commit and then finds
        # the order below. The unique constraint stays as the backstop.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"{buyer_id}:{idempotency_key}"},
        )
        seen = await session.scalar(
            select(Order).where(
                Order.buyer_id == buyer_id,
                Order.idempotency_key == idempotency_key,
            )
        )
        if seen is not None:
            return seen

    # Merge duplicate lines before locking. A line is a product *and* the
    # variant chosen, so two sizes of the same shirt stay two lines.
    wanted: dict[tuple[str, str | None], int] = {}
    for product_id, variant_id, qty in requested:
        key = (product_id, variant_id)
        wanted[key] = wanted.get(key, 0) + qty

    # Read the products (no lock — nothing here is decremented on them
    # unless they have no variants) and find out which ones oblige a choice.
    products: dict[str, Product] = {}
    for product_id in {pid for pid, _ in wanted}:
        product = await session.get(Product, product_id)
        if product is None or product.status != "ACTIVE":
            raise OrderError("UNAVAILABLE", "Product is no longer available")
        products[product_id] = product

    from app.products.store import ProductVariant, variant_label, variants_for

    catalogue = await variants_for(session, list(products))

    for (product_id, variant_id), _ in wanted.items():
        has_variants = bool(catalogue.get(product_id))
        if has_variants and variant_id is None:
            raise OrderError(
                "VARIANT_REQUIRED",
                f"Chọn phân loại cho {products[product_id].name}",
            )
        if variant_id is not None and not has_variants:
            raise OrderError("UNAVAILABLE", "Product has no such option")

    # Lock exactly the rows that will be decremented, in a fixed order:
    # two checkouts locking {A,B} and {B,A} would deadlock, both locking in
    # id order cannot. For a product with variants that row is the variant;
    # for a plain product it is the product itself.
    variants: dict[str, ProductVariant] = {}
    locked_products: dict[str, Product] = {}
    for lock_id, product_id, variant_id in sorted(
        (variant_id or product_id, product_id, variant_id)
        for product_id, variant_id in wanted
    ):
        if variant_id is None:
            # populate_existing is load-bearing, not tidiness: the product was
            # already read above, so without it session.get hands back the
            # identity-mapped object and never issues SELECT … FOR UPDATE —
            # the lock silently disappears and two buyers both win the last
            # unit. INV-05 dies quietly. (Caught by
            # test_two_buyers_race_for_the_last_unit.)
            locked = await session.get(
                Product, product_id, with_for_update=True, populate_existing=True
            )
            if locked is None or locked.status != "ACTIVE":
                raise OrderError("UNAVAILABLE", "Product is no longer available")
            locked_products[product_id] = locked
            products[product_id] = locked
        else:
            variant = await session.get(
                ProductVariant,
                variant_id,
                with_for_update=True,
                populate_existing=True,
            )
            if variant is None or variant.product_id != product_id:
                raise OrderError("UNAVAILABLE", "That option is no longer sold")
            variants[variant_id] = variant

    def _available(product_id: str, variant_id: str | None) -> int:
        if variant_id is None:
            return locked_products[product_id].stock
        return variants[variant_id].stock

    def _describe(product_id: str, variant_id: str | None) -> str:
        name = products[product_id].name
        if variant_id is None:
            return name
        return f"{name} ({variant_label(variants[variant_id])})"

    short = [
        _describe(product_id, variant_id)
        for (product_id, variant_id), qty in wanted.items()
        if _available(product_id, variant_id) < qty
    ]
    if short:
        raise OrderError(
            "OUT_OF_STOCK", f"Not enough stock for: {', '.join(sorted(short))}"
        )

    for (product_id, variant_id), qty in wanted.items():
        if variant_id is None:
            locked_products[product_id].stock -= qty
        else:
            variants[variant_id].stock -= qty

    by_shop: dict[str, list[tuple[str, str | None]]] = {}
    for product_id, variant_id in wanted:
        by_shop.setdefault(products[product_id].shop_id, []).append(
            (product_id, variant_id)
        )

    order = Order(
        id=str(uuid.uuid4()),
        buyer_id=buyer_id,
        address=address,
        total=Decimal("0"),
        idempotency_key=idempotency_key,
    )
    session.add(order)
    # Explicit flushes between the levels: these models carry no
    # relationship(), and without one the unit of work does NOT order
    # inserts by foreign key — it would happily write order_items before
    # shop_orders and hit the constraint. Flushing per level pins the
    # order; it all stays one transaction until the commit below.
    await session.flush()

    # Vouchers live right now, read once. The best applicable one applies
    # itself per shop — the buyer never types a code, and the same
    # `discount_for` that priced the product card prices the order, so the
    # advertised saving is the saving charged.
    from app.vouchers import store as vouchers

    live_vouchers = await vouchers.list_live(session)

    total = Decimal("0")
    shop_orders: list[ShopOrder] = []
    for shop_id in sorted(by_shop):
        # A variant may carry its own price (a 2XL, a 512GB); when it
        # doesn't, the product's price stands.
        def _unit(product_id: str, variant_id: str | None) -> Decimal:
            if variant_id is not None and variants[variant_id].price is not None:
                return variants[variant_id].price
            return products[product_id].price

        lines = [
            (products[pid].category, _unit(pid, vid) * wanted[(pid, vid)])
            for pid, vid in by_shop[shop_id]
        ]
        subtotal = sum((amount for _, amount in lines), Decimal("0"))
        applicable = [
            voucher
            for voucher in live_vouchers
            if voucher.shop_id is None or voucher.shop_id == shop_id
        ]
        # A code the buyer picked at checkout wins, as long as it is still
        # live, still theirs to use and still worth something; otherwise the
        # best one applies itself. Validated here, never trusted from the
        # request — a chosen code is a request for a discount, not proof of
        # one.
        voucher, discount = None, Decimal("0")
        wanted_code = (chosen or {}).get(shop_id)
        if wanted_code:
            for candidate in applicable:
                if candidate.code == wanted_code.upper():
                    picked = vouchers.discount_on(candidate, lines)
                    if picked > 0:
                        voucher, discount = candidate, picked
                    break
        if voucher is None:
            voucher, discount = vouchers.best_for(applicable, lines)

        shop_order = ShopOrder(
            id=str(uuid.uuid4()),
            order_id=order.id,
            shop_id=shop_id,
            subtotal=subtotal,
            shipping_fee=SHIPPING_FEE_PER_SHOP,
            discount=discount,
            voucher_code=voucher.code if voucher is not None else None,
        )
        session.add(shop_order)
        shop_orders.append(shop_order)
        total += subtotal - discount + SHIPPING_FEE_PER_SHOP
    await session.flush()

    for shop_order in shop_orders:
        for pid, vid in by_shop[shop_order.shop_id]:
            product = products[pid]
            variant = variants.get(vid) if vid else None
            unit_price = (
                variant.price
                if variant is not None and variant.price is not None
                else product.price
            )
            session.add(
                OrderItem(
                    id=str(uuid.uuid4()),
                    shop_order_id=shop_order.id,
                    product_id=pid,
                    name=product.name,
                    unit=product.unit,
                    price=unit_price,
                    qty=wanted[(pid, vid)],
                    # The swatch, when the variant has one — a receipt for a
                    # red shirt should not show the blue photo.
                    image_url=(
                        variant.image_url
                        if variant is not None and variant.image_url
                        else product.image_url
                    ),
                    variant_id=vid,
                    # Snapshotted like the price above: the seller may drop
                    # this option tomorrow, and the receipt must still read
                    # "Đen / L".
                    variant_label=variant_label(variant) if variant else None,
                )
            )

    order.total = total
    # One commit releases the locks and makes the whole order visible —
    # or nothing at all.
    await session.commit()
    await session.refresh(order)
    return order


async def quote(
    session: AsyncSession,
    requested: list[tuple[str, str | None, int]],
    chosen: dict[str, str] | None = None,
) -> dict:
    """Price a basket without placing it — what checkout previews.

    Runs the same grouping and the same voucher arithmetic as `place_order`,
    so the figure shown before confirming is the figure charged after. It
    takes no locks and writes nothing: stock is only checked for real inside
    the order transaction, where it can be held.
    """
    from app.products.store import ProductVariant
    from app.vouchers import store as vouchers

    wanted: dict[tuple[str, str | None], int] = {}
    for product_id, variant_id, qty in requested:
        key = (product_id, variant_id)
        wanted[key] = wanted.get(key, 0) + qty

    found: dict[str, Product] = {}
    variants: dict[str, ProductVariant] = {}
    for product_id, variant_id in wanted:
        if product_id not in found:
            product = await session.get(Product, product_id)
            if product is not None and product.status == "ACTIVE":
                found[product_id] = product
        if variant_id and variant_id not in variants:
            variant = await session.get(ProductVariant, variant_id)
            if variant is not None:
                variants[variant_id] = variant

    by_shop: dict[str, list[tuple[str, str | None]]] = {}
    for product_id, variant_id in wanted:
        product = found.get(product_id)
        if product is not None:
            by_shop.setdefault(product.shop_id, []).append(
                (product_id, variant_id)
            )

    live_vouchers = await vouchers.list_live(session)

    shops_view = []
    total = Decimal("0")
    merchandise = Decimal("0")
    discount_total = Decimal("0")
    for shop_id in sorted(by_shop):
        lines = [
            (
                found[pid].category,
                (
                    variants[vid].price
                    if vid and variants.get(vid) and variants[vid].price is not None
                    else found[pid].price
                )
                * wanted[(pid, vid)],
            )
            for pid, vid in by_shop[shop_id]
        ]
        subtotal = sum((amount for _, amount in lines), Decimal("0"))
        applicable = [
            voucher
            for voucher in live_vouchers
            if voucher.shop_id is None or voucher.shop_id == shop_id
        ]

        # Every voucher this shop offers, usable or not — checkout shows the
        # unusable ones greyed with the reason, so a buyer can see what they
        # would need to do to earn one.
        offers = vouchers.offers_for(applicable, lines)
        wanted_code = (chosen or {}).get(shop_id)
        picked = next(
            (
                offer
                for offer in offers
                if offer["applicable"]
                and wanted_code
                and offer["voucher"].code == wanted_code.upper()
            ),
            None,
        )
        if picked is not None:
            voucher, discount = picked["voucher"], picked["discount"]
        else:
            voucher, discount = vouchers.best_for(applicable, lines)

        shops_view.append(
            {
                "shopId": shop_id,
                "subtotal": float(subtotal),
                "discount": float(discount),
                "shippingFee": float(SHIPPING_FEE_PER_SHOP),
                "voucherCode": voucher.code if voucher is not None else None,
                "voucherDescription": (
                    voucher.description if voucher is not None else None
                ),
                "vouchers": [
                    {
                        "code": offer["voucher"].code,
                        "description": offer["voucher"].description,
                        "discount": float(offer["discount"]),
                        "applicable": offer["applicable"],
                        "reason": offer["reason"],
                        "endsAt": offer["voucher"].ends_at.isoformat(),
                    }
                    for offer in offers
                ],
            }
        )
        merchandise += subtotal
        discount_total += discount
        total += subtotal - discount + SHIPPING_FEE_PER_SHOP

    return {
        "merchandise": float(merchandise),
        "discount": float(discount_total),
        "shipping": float(len(by_shop) * SHIPPING_FEE_PER_SHOP),
        "total": float(total),
        "shops": shops_view,
    }


def hold_expires_at(order: Order) -> datetime | None:
    """When this order's stock goes back on sale, or None once it can't.

    Only a PENDING order holds anything: paying it makes the hold
    permanent, cancelling already gave the stock back.
    """
    if order.status != "PENDING":
        return None
    from app.config import settings

    expires = order.created_at + timedelta(minutes=settings.order_hold_minutes)
    if order.payment_started_at is not None:
        # A buyer at the payment screen gets longer: OTPs, bank apps and bad
        # signal all take time, and releasing their stock while their money
        # is moving is the one outcome worth paying to avoid.
        expires = max(
            expires,
            order.payment_started_at
            + timedelta(minutes=settings.payment_grace_minutes),
        )
    return expires


async def release_expired(session: AsyncSession) -> int:
    """Hand back the stock of orders that were never paid for.

    Placing an order decrements stock straight away, which is what stops
    two buyers claiming the last unit — but it also means an abandoned
    checkout would hold that unit for ever. This is the other half: after
    the hold window a PENDING order is cancelled and every line it took is
    returned to the row it came from.

    Rows are locked before being touched, and the order's own status is the
    guard against giving the same stock back twice — a cancelled order is
    no longer PENDING, so a second sweep skips it. `skip_locked` lets two
    concurrent sweeps share the work instead of blocking on each other.
    """
    from app.config import settings
    from app.products.store import Product as ProductRow
    from app.products.store import ProductVariant

    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.order_hold_minutes
    )

    payment_cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.payment_grace_minutes
    )
    candidates = list(
        await session.scalars(
            select(Order)
            .where(Order.status == "PENDING", Order.created_at < cutoff)
            .order_by(Order.created_at)
            .with_for_update(skip_locked=True)
        )
    )
    # An order with a payment session still inside its grace window is not
    # abandoned — someone is at the gateway with it.
    stale = [
        order
        for order in candidates
        if order.payment_started_at is None
        or order.payment_started_at < payment_cutoff
    ]
    if not stale:
        return 0

    order_ids = [order.id for order in stale]
    shop_order_ids = list(
        await session.scalars(
            select(ShopOrder.id).where(ShopOrder.order_id.in_(order_ids))
        )
    )
    items = list(
        await session.scalars(
            select(OrderItem).where(OrderItem.shop_order_id.in_(shop_order_ids))
        )
    )

    # Give each line back to the row it was taken from: the variant when one
    # was chosen, the product otherwise. A row the seller has since deleted
    # is skipped — there is nowhere to return it to, and inventing one would
    # be worse than losing it.
    for item in items:
        if item.variant_id:
            variant = await session.get(
                ProductVariant, item.variant_id, with_for_update=True
            )
            if variant is not None:
                variant.stock += item.qty
        else:
            product = await session.get(
                ProductRow, item.product_id, with_for_update=True
            )
            if product is not None:
                product.stock += item.qty

    for order in stale:
        order.status = "CANCELLED"

    await session.commit()
    return len(stale)


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


async def advance_simulated_fulfilment(session: AsyncSession) -> int:
    """Walk paid orders down the fulfilment ladder on a timer.

    There is no courier and no logistics feed behind this shop, so the
    delivery is simulated — but it is simulated *here*, on the rows the
    rest of the app reads, not in the buyer's tracker widget. That is the
    whole point: the tracker used to run its own clock, so it announced
    "Đã giao" while shop_orders.status still said CONFIRMED and every
    other screen still said "Chờ lấy hàng". One clock, one source of
    truth, and the two can no longer disagree.

    The clock starts when the buyer went to pay (falling back to when the
    order was placed), and the comparison is made in the database so a
    naive/aware datetime can never decide whether a parcel arrived.

    Delivering runs before shipping so an order older than both windows
    lands on DELIVERED in a single pass rather than crawling one stage per
    tick. A seller who fulfils by hand simply gets there first; this only
    moves what is still lagging, and never touches CANCELLED.
    """
    from app.config import settings

    if not settings.fulfilment_sim_enabled:
        return 0

    now = datetime.now(timezone.utc)
    started = func.coalesce(Order.payment_started_at, Order.created_at)

    async def due(from_statuses: list[str], after_seconds: int) -> list[ShopOrder]:
        cutoff = now - timedelta(seconds=after_seconds)
        return list(
            (
                await session.execute(
                    select(ShopOrder)
                    .join(Order, Order.id == ShopOrder.order_id)
                    .where(
                        Order.status == "PAID",
                        ShopOrder.status.in_(from_statuses),
                        started < cutoff,
                    )
                    .with_for_update(skip_locked=True, of=ShopOrder)
                )
            )
            .scalars()
            .all()
        )

    moved = 0
    for shop_order in await due(
        ["CONFIRMED", "SHIPPING"], settings.fulfilment_deliver_after_seconds
    ):
        shop_order.status = "DELIVERED"
        moved += 1
    for shop_order in await due(
        ["CONFIRMED"], settings.fulfilment_ship_after_seconds
    ):
        shop_order.status = "SHIPPING"
        moved += 1

    if moved:
        await session.commit()
    return moved


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


async def find_by_idempotency_key(
    session: AsyncSession, buyer_id: str, key: str | None
) -> Order | None:
    """The order a given checkout key already produced, if any."""
    if not key:
        return None
    return await session.scalar(
        select(Order).where(
            Order.buyer_id == buyer_id, Order.idempotency_key == key
        )
    )


async def cancel_by_buyer(
    session: AsyncSession, order_id: str, buyer_id: str
) -> tuple[Order | None, str]:
    """Let a buyer call off an order, while that is still fair to the shop.

    Allowed until a shop starts working on it: every slice must still be
    CONFIRMED. Once anything is SHIPPING the goods are moving and calling it
    off is a returns problem, not a cancellation — so it is refused rather
    than quietly accepted.

    The stock goes back the same way the expiry sweep returns it, and the
    order's status is again the guard against crediting twice.
    """
    from app.products.store import Product as ProductRow
    from app.products.store import ProductVariant

    order = await session.get(
        Order, order_id, with_for_update=True, populate_existing=True
    )
    if order is None or order.buyer_id != buyer_id:
        return None, "NOT_FOUND"
    if order.status == "CANCELLED":
        return order, "ALREADY_CANCELLED"
    if order.status not in ("PENDING", "PAID"):
        return order, "NOT_CANCELLABLE"

    shop_orders = list(
        await session.scalars(
            select(ShopOrder).where(ShopOrder.order_id == order.id)
        )
    )
    if any(so.status != "CONFIRMED" for so in shop_orders):
        return order, "ALREADY_SHIPPING"

    items = list(
        await session.scalars(
            select(OrderItem).where(
                OrderItem.shop_order_id.in_([so.id for so in shop_orders])
            )
        )
    )
    for item in items:
        if item.variant_id:
            variant = await session.get(
                ProductVariant, item.variant_id, with_for_update=True
            )
            if variant is not None:
                variant.stock += item.qty
        else:
            product = await session.get(
                ProductRow, item.product_id, with_for_update=True
            )
            if product is not None:
                product.stock += item.qty

    for shop_order in shop_orders:
        shop_order.status = "CANCELLED"
    order.status = "CANCELLED"

    await session.commit()
    await session.refresh(order)
    return order, "CANCELLED"


async def attach_payment(
    session: AsyncSession, order_id: str, buyer_id: str, payment_id: str
) -> Order | None:
    """Remember which gateway session is paying for this order."""
    order = await session.get(Order, order_id, with_for_update=True)
    if order is None or order.buyer_id != buyer_id or order.status != "PENDING":
        return None
    order.payment_id = payment_id
    order.payment_started_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(order)
    return order


async def pending_with_payments(
    session: AsyncSession, older_than_seconds: int
) -> list[Order]:
    """Unpaid orders whose payment session is old enough to be worth asking
    the gateway about — young ones are simply still in progress."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
    rows = await session.scalars(
        select(Order).where(
            Order.status == "PENDING",
            Order.payment_id.is_not(None),
            Order.payment_started_at < cutoff,
        )
    )
    return list(rows)


async def reconcile_pending(
    session: AsyncSession, older_than_seconds: int = 60
) -> dict:
    """Ask the gateway about payments we never heard back about.

    Webhooks get lost — the merchant's server is down for a minute, a
    retry budget runs out, a network eats it. The buyer's money still
    moved. Polling is the only way to find out, and a marketplace that
    doesn't do it silently keeps money it did not deliver against.

    Returns a small summary so the caller can log or surface it.
    """
    from app.payments import gateway

    checked = paid = 0
    for order in await pending_with_payments(session, older_than_seconds):
        checked += 1
        state = await gateway.query(order.payment_id or "")
        if state is None or state.get("status") != "PAID":
            continue
        # Same path a webhook takes, including the amount check, so a
        # gateway that reports a different figure is refused here too.
        _, result = await mark_paid(session, order.id, Decimal(state["amount"]))
        if result == "PAID":
            paid += 1

    return {"checked": checked, "recovered": paid}
