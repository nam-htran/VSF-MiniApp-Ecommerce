"""V-Market users.

`role` is V-Market's data, not V-App's. V-App only returns an identity —
it has no notion of buyer or seller.
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
    # Everyone arrives a BUYER. Opening a shop is what makes a SELLER, so
    # there is no list of privileged accounts anywhere.
    role: Mapped[str] = mapped_column(default="BUYER")
    name: Mapped[str | None] = mapped_column(default=None)
    phone_number: Mapped[str | None] = mapped_column(default=None)


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
    user = MarketUser(
        id=str(uuid.uuid4()),
        vapp_user_id=vapp_user_id,
        role="BUYER",
        name=name,
        phone_number=phone_number,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def promote_to_seller(
    session: AsyncSession, user: MarketUser
) -> MarketUser:
    """Called when a shop is opened. A seller keeps buying from other shops."""
    user.role = "SELLER"
    await session.commit()
    await session.refresh(user)
    return user
