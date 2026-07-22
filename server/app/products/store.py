"""Products belonging to a shop."""

import uuid
from decimal import Decimal
from typing import Literal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, select
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
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), index=True)
    name: Mapped[str]
    description: Mapped[str]
    # Numeric, never Float: 0.1 + 0.2 != 0.3 in binary floating point, and a
    # basket of twenty lines would drift away from the price the buyer saw.
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock: Mapped[int]
    image_url: Mapped[str | None] = mapped_column(default=None)
    # HIDDEN keeps a product out of the storefront without deleting it —
    # past orders still reference it.
    status: Mapped[str] = mapped_column(default="ACTIVE")


async def find_by_id(session: AsyncSession, product_id: str) -> Product | None:
    return await session.get(Product, product_id)


async def list_for_shop(
    session: AsyncSession,
    shop_id: str,
    limit: int,
    offset: int,
    include_hidden: bool = False,
) -> list[Product]:
    """Products of one shop.

    `include_hidden` is for the seller looking at their own shop; buyers
    must never see it set.
    """
    query = select(Product).where(Product.shop_id == shop_id)
    if not include_hidden:
        query = query.where(Product.status == "ACTIVE")

    rows = await session.scalars(
        # Ordered so paging is stable — without it Postgres may return rows
        # in any order and one product can appear on two pages.
        query.order_by(Product.name, Product.id).limit(limit).offset(offset)
    )
    return list(rows)


async def create_product(
    session: AsyncSession,
    shop_id: str,
    name: str,
    description: str,
    price: Decimal,
    stock: int,
    image_url: str | None,
) -> Product:
    product = Product(
        id=str(uuid.uuid4()),
        shop_id=shop_id,
        name=name,
        description=description,
        price=price,
        stock=stock,
        image_url=image_url,
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
) -> Product:
    if name is not None:
        product.name = name
    if description is not None:
        product.description = description
    if price is not None:
        product.price = price
    if stock is not None:
        product.stock = stock
    if image_url is not None:
        product.image_url = image_url
    if status is not None:
        product.status = status

    await session.commit()
    await session.refresh(product)
    return product
