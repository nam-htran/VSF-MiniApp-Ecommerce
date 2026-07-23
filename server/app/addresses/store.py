"""A buyer's saved delivery addresses — an address book.

One person keeps several places to ship to and picks one at checkout. The
addresses belong to the user, so every query is scoped by user_id and the
routes never trust an id from the client without checking ownership.

Exactly one address is the default at a time: setting one clears the rest,
and deleting the default promotes the next-newest so the book is never left
without one while it still has entries.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_name: Mapped[str]
    phone: Mapped[str]
    # The location text — structured or free-form, plus an optional GPS pin.
    # Recipient and phone are kept apart so they can be shown and edited.
    address_line: Mapped[str]
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


async def list_for_user(session: AsyncSession, user_id: str) -> list[Address]:
    rows = await session.scalars(
        select(Address)
        .where(Address.user_id == user_id)
        .order_by(Address.is_default.desc(), Address.created_at.desc())
    )
    return list(rows)


async def _clear_default(session: AsyncSession, user_id: str) -> None:
    await session.execute(
        update(Address)
        .where(Address.user_id == user_id, Address.is_default.is_(True))
        .values(is_default=False)
    )


async def create(
    session: AsyncSession,
    user_id: str,
    recipient_name: str,
    phone: str,
    address_line: str,
    make_default: bool,
) -> Address:
    # The first address is always the default; after that, only if asked.
    existing = await session.scalar(
        select(func.count()).select_from(Address).where(Address.user_id == user_id)
    )
    is_default = make_default or existing == 0
    if is_default:
        await _clear_default(session, user_id)

    address = Address(
        id=str(uuid.uuid4()),
        user_id=user_id,
        recipient_name=recipient_name,
        phone=phone,
        address_line=address_line,
        is_default=is_default,
    )
    session.add(address)
    await session.commit()
    await session.refresh(address)
    return address


async def find_owned(
    session: AsyncSession, user_id: str, address_id: str
) -> Address | None:
    address = await session.get(Address, address_id)
    if address is None or address.user_id != user_id:
        return None
    return address


async def set_default(
    session: AsyncSession, user_id: str, address: Address
) -> Address:
    await _clear_default(session, user_id)
    address.is_default = True
    await session.commit()
    await session.refresh(address)
    return address


async def delete(session: AsyncSession, user_id: str, address: Address) -> None:
    was_default = address.is_default
    await session.delete(address)
    await session.flush()
    # Don't leave the book without a default while entries remain.
    if was_default:
        next_up = await session.scalar(
            select(Address)
            .where(Address.user_id == user_id)
            .order_by(Address.created_at.desc())
            .limit(1)
        )
        if next_up is not None:
            next_up.is_default = True
    await session.commit()
