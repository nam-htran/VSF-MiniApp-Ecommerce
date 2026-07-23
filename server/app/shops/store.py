import uuid
from typing import Literal

from sqlalchemy import ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ShopStatus = Literal["ACTIVE", "LOCKED"]


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[str] = mapped_column(primary_key=True)
    # unique=True is what enforces one seller, one shop. A plain `if
    # already_has_shop` check loses to two concurrent requests; a database
    # constraint does not.
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), unique=True, index=True
    )
    name: Mapped[str]
    description: Mapped[str]
    image_url: Mapped[str | None] = mapped_column(default=None)
    # Contact and origin. `province` is kept apart from the free-text
    # address so delivery time can be estimated from it (see the product
    # page) without parsing a string.
    address: Mapped[str | None] = mapped_column(default=None)
    phone: Mapped[str | None] = mapped_column(default=None)
    province: Mapped[str | None] = mapped_column(default=None)
    # The proposal activates a shop once the required fields are present,
    # which the create endpoint already enforces. LOCKED is here for later.
    status: Mapped[str] = mapped_column(default="ACTIVE")


async def find_by_id(session: AsyncSession, shop_id: str) -> Shop | None:
    return await session.get(Shop, shop_id)


async def find_by_owner(session: AsyncSession, owner_id: str) -> Shop | None:
    return await session.scalar(select(Shop).where(Shop.owner_id == owner_id))


async def list_active(
    session: AsyncSession, limit: int, offset: int
) -> list[Shop]:
    """Shops a buyer may browse. Ordered by name so paging is stable —
    without an ORDER BY, Postgres may return rows in any order and the
    same shop can appear on two pages."""
    rows = await session.scalars(
        select(Shop)
        .where(Shop.status == "ACTIVE")
        .order_by(Shop.name, Shop.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows)


async def create_shop(
    session: AsyncSession,
    owner_id: str,
    name: str,
    description: str,
    image_url: str | None,
    address: str | None = None,
    phone: str | None = None,
    province: str | None = None,
) -> Shop:
    shop = Shop(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        name=name,
        description=description,
        image_url=image_url,
        address=address,
        phone=phone,
        province=province,
    )
    session.add(shop)
    await session.commit()
    await session.refresh(shop)
    return shop


async def update_shop(
    session: AsyncSession,
    shop: Shop,
    name: str | None,
    description: str | None,
    image_url: str | None,
    address: str | None = None,
    phone: str | None = None,
    province: str | None = None,
) -> Shop:
    if name is not None:
        shop.name = name
    if description is not None:
        shop.description = description
    if image_url is not None:
        shop.image_url = image_url
    if address is not None:
        shop.address = address
    if phone is not None:
        shop.phone = phone
    if province is not None:
        shop.province = province

    await session.commit()
    await session.refresh(shop)
    return shop
