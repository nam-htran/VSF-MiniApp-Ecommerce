"""Product reviews — a star rating and a comment.

Only a buyer who actually paid for the product may review it: the check
walks their PAID orders for the item, the same evidence a real marketplace
requires so ratings mean something. One review per person per product,
enforced by a unique constraint and updated in place if they rate again.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.orders.store import Order, OrderItem, ShopOrder
from app.users.store import MarketUser


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        # One review per buyer per product; rating stays within 1..5 at the
        # database, not only in the request model.
        UniqueConstraint("product_id", "user_id", name="uq_reviews_product_user"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[int]
    comment: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


async def has_purchased(
    session: AsyncSession, user_id: str, product_id: str
) -> bool:
    """True when the user has a PAID order that includes this product."""
    found = await session.scalar(
        select(OrderItem.id)
        .join(ShopOrder, ShopOrder.id == OrderItem.shop_order_id)
        .join(Order, Order.id == ShopOrder.order_id)
        .where(
            Order.buyer_id == user_id,
            Order.status == "PAID",
            OrderItem.product_id == product_id,
        )
        .limit(1)
    )
    return found is not None


async def find_by_user(
    session: AsyncSession, product_id: str, user_id: str
) -> Review | None:
    return await session.scalar(
        select(Review).where(
            Review.product_id == product_id, Review.user_id == user_id
        )
    )


async def upsert(
    session: AsyncSession,
    product_id: str,
    user_id: str,
    rating: int,
    comment: str | None,
) -> Review:
    review = await find_by_user(session, product_id, user_id)
    if review is None:
        review = Review(
            id=str(uuid.uuid4()),
            product_id=product_id,
            user_id=user_id,
            rating=rating,
            comment=comment,
        )
        session.add(review)
    else:
        review.rating = rating
        review.comment = comment
    await session.commit()
    await session.refresh(review)
    return review


async def list_for_product(
    session: AsyncSession, product_id: str, limit: int, offset: int
) -> list[tuple[Review, str | None]]:
    rows = await session.execute(
        select(Review, MarketUser.name)
        .join(MarketUser, MarketUser.id == Review.user_id)
        .where(Review.product_id == product_id)
        .order_by(Review.created_at.desc(), Review.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all())


async def summary(session: AsyncSession, product_id: str) -> tuple[float, int]:
    """Average rating and count — 0 / 0 when there are no reviews yet."""
    average, count = (
        await session.execute(
            select(func.avg(Review.rating), func.count()).where(
                Review.product_id == product_id
            )
        )
    ).one()
    return (round(float(average), 1) if average is not None else 0.0, count)
