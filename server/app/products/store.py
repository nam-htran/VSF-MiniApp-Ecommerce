"""Products belonging to a shop."""

import json
import uuid
from decimal import Decimal
from typing import Literal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Numeric,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ProductStatus = Literal["ACTIVE", "HIDDEN"]


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        # The last line of defence for INV-05. Stock is decremented under a
        # row lock at checkout, but a bug in that logic must not be able to
        # sell a tenth copy of a nine-copy product — the database refuses.
        CheckConstraint("stock >= 0", name="ck_products_stock_non_negative"),
        CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
        # A sale where the old price is not higher is not a sale. Enforced
        # here so no code path can fake a discount badge.
        CheckConstraint(
            "original_price IS NULL OR original_price > price",
            name="ck_products_original_price_above_price",
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), index=True)
    name: Mapped[str]
    description: Mapped[str]
    # "Hũ 300g", "Túi 5kg" — the pack-size line on the card.
    unit: Mapped[str | None] = mapped_column(default=None)
    # Numeric, never Float: 0.1 + 0.2 != 0.3 in binary floating point, and a
    # basket of twenty lines would drift away from the price the buyer saw.
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Set = the product is on sale; this is the struck-through price. The
    # discount percentage is derived, never stored — two numbers cannot
    # drift apart.
    original_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), default=None
    )
    stock: Mapped[int]
    # A category key (e.g. "dien-tu"); the labels/emoji live on the client.
    # Null = uncategorised, still browsable, just not under any chip.
    category: Mapped[str | None] = mapped_column(default=None, index=True)
    # image_url is the cover (kept for the cards); image_urls is the full
    # gallery the detail page swipes through. The cover is always the first
    # of the gallery, so the two never disagree.
    image_url: Mapped[str | None] = mapped_column(default=None)
    image_urls: Mapped[list | None] = mapped_column(JSON, default=None)
    # HIDDEN keeps a product out of the storefront without deleting it —
    # past orders still reference it.
    status: Mapped[str] = mapped_column(default="ACTIVE")


class ProductVariant(Base):
    """One buyable combination — "Đen / Size L" — with its own stock.

    A product either has no variants (stock lives on the product, as
    before) or has them, and then stock lives *only* here. Keeping a second
    running total on the product would be two sources of truth for the one
    number this shop must never get wrong, so `products.stock` is simply
    ignored once variants exist, and the storefront shows the sum.
    """

    __tablename__ = "product_variants"
    __table_args__ = (
        # Same last line of defence as products.stock: checkout decrements
        # under a row lock, and the database refuses to go negative even if
        # that logic is wrong.
        CheckConstraint("stock >= 0", name="ck_variants_stock_non_negative"),
        CheckConstraint(
            "price IS NULL OR price >= 0", name="ck_variants_price_non_negative"
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id"), index=True
    )
    # {"Màu sắc": "Đen", "Size": "L"} — the seller names the groups, so a
    # shop selling shoes can say "Size" and one selling paint can say "Dung
    # tích" without a schema change.
    options: Mapped[dict] = mapped_column(JSON)
    # Null = sell at the product's price. Set only when one combination
    # genuinely costs more (a 2XL, a 512GB).
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    stock: Mapped[int] = mapped_column(default=0)
    # The swatch shown on the colour chip, when the seller uploads one.
    image_url: Mapped[str | None] = mapped_column(default=None)
    # The seller's own order. Sorting by id would scramble uuids and show
    # sizes as 39, 41, 42, 43, 40; sorting by label would put 2XL before S.
    # Only the person who typed the list knows the right order.
    position: Mapped[int] = mapped_column(default=0, server_default="0")


def variant_label(variant: ProductVariant) -> str:
    """"Đen / L" — what a receipt and a cart line show."""
    return " / ".join(str(value) for value in (variant.options or {}).values())


async def find_by_id(session: AsyncSession, product_id: str) -> Product | None:
    return await session.get(Product, product_id)


async def variants_for(
    session: AsyncSession, product_ids: list[str]
) -> dict[str, list[ProductVariant]]:
    """Variants of the given products, grouped by product id."""
    if not product_ids:
        return {}
    rows = await session.scalars(
        select(ProductVariant)
        .where(ProductVariant.product_id.in_(product_ids))
        .order_by(ProductVariant.position, ProductVariant.id)
    )
    grouped: dict[str, list[ProductVariant]] = {}
    for variant in rows:
        grouped.setdefault(variant.product_id, []).append(variant)
    return grouped


async def replace_variants(
    session: AsyncSession, product: Product, variants: list[dict]
) -> list[ProductVariant]:
    """Rewrite a product's variants to exactly what the seller submitted.

    Rows are matched by their options, so editing quantities keeps the same
    variant ids — orders already placed still point at a row that exists,
    and a stock number is not silently reset by an unrelated edit.
    """
    existing = {
        json.dumps(v.options, sort_keys=True, ensure_ascii=False): v
        for v in (await variants_for(session, [product.id])).get(product.id, [])
    }

    kept: list[ProductVariant] = []
    for position, incoming in enumerate(variants):
        key = json.dumps(incoming["options"], sort_keys=True, ensure_ascii=False)
        variant = existing.pop(key, None)
        if variant is None:
            variant = ProductVariant(
                id=str(uuid.uuid4()),
                product_id=product.id,
                options=incoming["options"],
            )
            session.add(variant)
        variant.stock = incoming["stock"]
        variant.price = incoming.get("price")
        variant.image_url = incoming.get("image_url")
        variant.position = position
        kept.append(variant)

    # Whatever the seller removed goes; past order items snapshot their own
    # name and price, so a deleted variant cannot damage a receipt.
    for orphan in existing.values():
        await session.delete(orphan)

    await session.commit()
    return kept


def _escape_like(text: str) -> str:
    """Neutralise LIKE wildcards so a user's % or _ is matched literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _metric_subqueries():
    """Per-product average rating and units sold, as subqueries to left-join
    onto a listing — so the cards can show stars and "đã bán" without an
    N+1. Imported locally to sidestep the products↔orders/reviews cycle."""
    from app.orders.store import Order, OrderItem, ShopOrder
    from app.reviews.store import Review

    rating = (
        select(
            Review.product_id.label("pid"),
            func.avg(Review.rating).label("avg"),
            func.count().label("cnt"),
        )
        .group_by(Review.product_id)
        .subquery()
    )
    # Sold = quantity in orders that actually paid.
    sold = (
        select(
            OrderItem.product_id.label("pid"),
            func.sum(OrderItem.qty).label("sold"),
        )
        .join(ShopOrder, ShopOrder.id == OrderItem.shop_order_id)
        .join(Order, Order.id == ShopOrder.order_id)
        .where(Order.status == "PAID")
        .group_by(OrderItem.product_id)
        .subquery()
    )
    return rating, sold


def _metrics(avg, cnt, sold) -> dict:
    return {
        "ratingAverage": round(float(avg), 1) if avg is not None else 0.0,
        "ratingCount": cnt or 0,
        "sold": int(sold) if sold is not None else 0,
    }


async def list_active(
    session: AsyncSession,
    limit: int,
    offset: int,
    on_sale: bool = False,
    q: str | None = None,
) -> list[dict]:
    """The marketplace storefront: active products across all shops, each
    with the card's data — shop name and province (for the delivery
    estimate), average rating, and units sold.

    Joined here rather than fetched per product: N cards must not cost N+1
    queries, and the response budget is under a second.

    `q` filters by product name or shop name, case-insensitively — the
    search box, moved off the client so it covers the whole catalogue.
    """
    from app.shops.store import Shop

    rating, sold = _metric_subqueries()
    query = (
        select(
            Product,
            Shop.name,
            Shop.province,
            rating.c.avg,
            rating.c.cnt,
            sold.c.sold,
        )
        .join(Shop, Shop.id == Product.shop_id)
        .outerjoin(rating, rating.c.pid == Product.id)
        .outerjoin(sold, sold.c.pid == Product.id)
        .where(Product.status == "ACTIVE", Shop.status == "ACTIVE")
    )
    if on_sale:
        # On sale = has a struck-through price. No separate flag to drift.
        query = query.where(Product.original_price.is_not(None))
    if q and q.strip():
        like = f"%{_escape_like(q.strip())}%"
        query = query.where(
            or_(
                Product.name.ilike(like, escape="\\"),
                Shop.name.ilike(like, escape="\\"),
            )
        )

    rows = await session.execute(
        # Ordered so paging is stable — without it Postgres may return
        # rows in any order and one product can appear on two pages.
        query.order_by(Product.name, Product.id).limit(limit).offset(offset)
    )
    return [
        {
            "product": product,
            "shopName": shop_name,
            "shopProvince": province,
            **_metrics(avg, cnt, sold_qty),
        }
        for product, shop_name, province, avg, cnt, sold_qty in rows.all()
    ]


async def list_for_shop(
    session: AsyncSession,
    shop_id: str,
    limit: int,
    offset: int,
    include_hidden: bool = False,
) -> list[dict]:
    """Products of one shop, carrying the same card data as the storefront
    (province, rating, sold) so the "more from this shop" strip matches.

    `include_hidden` is for the seller looking at their own shop; buyers
    must never see it set.
    """
    from app.shops.store import Shop

    rating, sold = _metric_subqueries()
    query = (
        select(
            Product,
            Shop.name,
            Shop.province,
            rating.c.avg,
            rating.c.cnt,
            sold.c.sold,
        )
        .join(Shop, Shop.id == Product.shop_id)
        .outerjoin(rating, rating.c.pid == Product.id)
        .outerjoin(sold, sold.c.pid == Product.id)
        .where(Product.shop_id == shop_id)
    )
    if not include_hidden:
        query = query.where(Product.status == "ACTIVE")

    rows = await session.execute(
        # Ordered so paging is stable — without it Postgres may return rows
        # in any order and one product can appear on two pages.
        query.order_by(Product.name, Product.id).limit(limit).offset(offset)
    )
    return [
        {
            "product": product,
            "shopName": shop_name,
            "shopProvince": province,
            **_metrics(avg, cnt, sold_qty),
        }
        for product, shop_name, province, avg, cnt, sold_qty in rows.all()
    ]


async def create_product(
    session: AsyncSession,
    shop_id: str,
    name: str,
    description: str,
    price: Decimal,
    stock: int,
    image_url: str | None,
    unit: str | None = None,
    original_price: Decimal | None = None,
    image_urls: list[str] | None = None,
    category: str | None = None,
) -> Product:
    gallery = image_urls or ([image_url] if image_url else None)
    product = Product(
        id=str(uuid.uuid4()),
        shop_id=shop_id,
        name=name,
        description=description,
        unit=unit,
        price=price,
        original_price=original_price,
        stock=stock,
        category=category,
        # The cover is the first of the gallery.
        image_url=gallery[0] if gallery else None,
        image_urls=gallery,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def update_product(
    session: AsyncSession,
    product: Product,
    name: str | None = None,
    description: str | None = None,
    price: Decimal | None = None,
    stock: int | None = None,
    image_url: str | None = None,
    status: str | None = None,
    image_urls: list[str] | None = None,
    category: str | None = None,
) -> Product:
    if category is not None:
        product.category = category
    if name is not None:
        product.name = name
    if description is not None:
        product.description = description
    if price is not None:
        product.price = price
    if stock is not None:
        product.stock = stock
    if image_urls is not None:
        # Replace the whole gallery; the cover follows the first image.
        product.image_urls = image_urls or None
        product.image_url = image_urls[0] if image_urls else None
    elif image_url is not None:
        product.image_url = image_url
    if status is not None:
        product.status = status

    await session.commit()
    await session.refresh(product)
    return product
