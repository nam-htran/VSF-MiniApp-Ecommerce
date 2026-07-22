"""V-Market users.

`role` and `seller_id` are V-Market's data, not V-App's. V-App only
returns an identity — it has no notion of buyer or seller.
"""

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

UserRole = Literal["BUYER", "SELLER"]


class MarketUser(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(primary_key=True)
    # Unique: two rows for one person would split their orders in half.
    vapp_user_id: Mapped[str] = mapped_column(unique=True, index=True)
    role: Mapped[str]
    seller_id: Mapped[str | None] = mapped_column(default=None)
    name: Mapped[str | None] = mapped_column(default=None)
    phone_number: Mapped[str | None] = mapped_column(default=None)


# Roles for the demo accounts. Deliberately a V-Market-side table, so the
# boundary with V-App stays visible.
_SEED_ROLES: dict[str, tuple[UserRole, str | None]] = {
    "11111111-1111-4111-8111-111111111111": ("BUYER", None),
    "22222222-2222-4222-8222-222222222222": ("SELLER", "seller-a"),
    "33333333-3333-4333-8333-333333333333": ("SELLER", "seller-b"),
}


async def find_by_id(session: AsyncSession, user_id: str) -> MarketUser | None:
    return await session.get(MarketUser, user_id)


async def find_by_vapp_user_id(
    session: AsyncSession, vapp_user_id: str
) -> MarketUser | None:
    return await session.scalar(
        select(MarketUser).where(MarketUser.vapp_user_id == vapp_user_id)
    )


async def create_user(
    session: AsyncSession,
    vapp_user_id: str,
    name: str | None,
    phone_number: str | None,
) -> MarketUser:
    # New users default to BUYER; becoming a SELLER is a separate action
    # (creating a shop, day 3).
    role, seller_id = _SEED_ROLES.get(vapp_user_id, ("BUYER", None))

    user = MarketUser(
        id=str(uuid.uuid4()),
        vapp_user_id=vapp_user_id,
        role=role,
        seller_id=seller_id,
        name=name,
        phone_number=phone_number,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
