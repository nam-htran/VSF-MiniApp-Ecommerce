"""Persistence for product-feed reactions and comments."""

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.users.store import MarketUser

ReactionType = Literal["LIKE", "LOVE", "HAHA", "WOW", "SAD"]


class FeedReaction(Base):
    __tablename__ = "feed_reactions"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "user_id", name="uq_feed_reactions_product_user"
        ),
        CheckConstraint(
            "reaction_type IN ('LIKE', 'LOVE', 'HAHA', 'WOW', 'SAD')",
            name="ck_feed_reactions_type",
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    reaction_type: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FeedComment(Base):
    __tablename__ = "feed_comments"

    id: Mapped[str] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


async def summaries_for_products(
    session: AsyncSession, product_ids: list[str], user_id: str | None
) -> dict[str, dict]:
    """Counts plus the current user's reaction, in three bulk queries."""
    summaries = {
        product_id: {
            "reactionCount": 0,
            "commentCount": 0,
            "reactedByMe": False,
            "reactionType": None,
        }
        for product_id in product_ids
    }
    if not product_ids:
        return summaries

    reaction_rows = await session.execute(
        select(FeedReaction.product_id, func.count(FeedReaction.id))
        .where(FeedReaction.product_id.in_(product_ids))
        .group_by(FeedReaction.product_id)
    )
    for product_id, count in reaction_rows:
        summaries[product_id]["reactionCount"] = count

    comment_rows = await session.execute(
        select(FeedComment.product_id, func.count(FeedComment.id))
        .where(FeedComment.product_id.in_(product_ids))
        .group_by(FeedComment.product_id)
    )
    for product_id, count in comment_rows:
        summaries[product_id]["commentCount"] = count

    if user_id:
        mine = await session.execute(
            select(FeedReaction.product_id, FeedReaction.reaction_type).where(
                FeedReaction.product_id.in_(product_ids),
                FeedReaction.user_id == user_id,
            )
        )
        for product_id, reaction_type in mine:
            summaries[product_id]["reactedByMe"] = True
            summaries[product_id]["reactionType"] = reaction_type

    return summaries


async def reaction_count(session: AsyncSession, product_id: str) -> int:
    return await session.scalar(
        select(func.count(FeedReaction.id)).where(
            FeedReaction.product_id == product_id
        )
    ) or 0


async def set_reaction(
    session: AsyncSession,
    product_id: str,
    user_id: str,
    reaction_type: ReactionType,
) -> int:
    statement = insert(FeedReaction).values(
        id=str(uuid.uuid4()),
        product_id=product_id,
        user_id=user_id,
        reaction_type=reaction_type,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_feed_reactions_product_user",
        set_={"reaction_type": reaction_type},
    )
    await session.execute(statement)
    await session.commit()
    return await reaction_count(session, product_id)


async def remove_reaction(
    session: AsyncSession, product_id: str, user_id: str
) -> int:
    await session.execute(
        delete(FeedReaction).where(
            FeedReaction.product_id == product_id,
            FeedReaction.user_id == user_id,
        )
    )
    await session.commit()
    return await reaction_count(session, product_id)


async def create_comment(
    session: AsyncSession, product_id: str, user_id: str, content: str
) -> FeedComment:
    comment = FeedComment(
        id=str(uuid.uuid4()),
        product_id=product_id,
        user_id=user_id,
        content=content,
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return comment


async def list_comments(
    session: AsyncSession, product_id: str, limit: int, offset: int
) -> list[tuple[FeedComment, str | None]]:
    rows = await session.execute(
        select(FeedComment, MarketUser.name)
        .join(MarketUser, MarketUser.id == FeedComment.user_id)
        .where(FeedComment.product_id == product_id)
        .order_by(FeedComment.created_at.desc(), FeedComment.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all())


async def comment_count(session: AsyncSession, product_id: str) -> int:
    return await session.scalar(
        select(func.count(FeedComment.id)).where(
            FeedComment.product_id == product_id
        )
    ) or 0


async def find_comment(
    session: AsyncSession, comment_id: str
) -> FeedComment | None:
    return await session.get(FeedComment, comment_id)


async def delete_comment(session: AsyncSession, comment: FeedComment) -> None:
    await session.delete(comment)
    await session.commit()
