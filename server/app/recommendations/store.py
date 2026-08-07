"""Browsing history, and what to recommend from it.

The history is the point. A sequential recommender is fed the sequence of
things a shopper looked at — `prev_items` in the Amazon-M2 training data —
and orders alone could never supply that: people look at far more than they
buy, and the looking is where the intent shows.

Recall runs on Semantic IDs. Every product carries the three codes the
RQ-VAE assigned it, coarse to fine, and two products sharing a prefix are
near each other in the embedding space the model learned. So "more like what
you have been looking at" is a prefix match, and how much of the prefix
matches is how close the match is.

This is deliberately not the Transformer. The Transformer *generates* the
next Semantic ID rather than looking one up, which is a stronger claim and
needs a trained checkpoint. Both answer the same question and both return
products, so when the checkpoint exists it slots in behind `recommend`
without the routes or the client noticing.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.products import store as products
from app.products.store import Product

# How much history to reason from. Long enough to see a theme, short enough
# that yesterday's browsing does not drown what they are looking at now.
HISTORY_DEPTH = 10


class ProductView(Base):
    """One product opened by one shopper, once per opening.

    Repeats are kept rather than collapsed: looking at the same product four
    times says something a single row would lose.
    """

    __tablename__ = "product_views"

    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


async def record_view(session: AsyncSession, user_id: str, product_id: str) -> None:
    session.add(
        ProductView(
            id=str(uuid.uuid4()), user_id=user_id, product_id=product_id
        )
    )
    await session.commit()


async def recent_views(
    session: AsyncSession, user_id: str, limit: int = HISTORY_DEPTH
) -> list[str]:
    """The last products this shopper opened, newest first, no repeats.

    Deduplicated here rather than in SQL: the rows are few and keeping the
    "newest occurrence wins" rule in Python is plainer than a window
    function that says the same thing.
    """
    result = await session.execute(
        select(ProductView.product_id)
        .where(ProductView.user_id == user_id)
        .order_by(ProductView.viewed_at.desc())
        .limit(limit * 4)
    )
    seen: dict[str, None] = {}
    for (product_id,) in result.all():
        seen.setdefault(product_id, None)
        if len(seen) >= limit:
            break
    return list(seen)


async def _semantic_ids(
    session: AsyncSession, product_ids: list[str]
) -> list[tuple[int, int, int]]:
    if not product_ids:
        return []
    result = await session.execute(
        select(Product.sid_0, Product.sid_1, Product.sid_2).where(
            Product.id.in_(product_ids), Product.sid_0.is_not(None)
        )
    )
    return [(a, b, c) for a, b, c in result.all()]


def _match_depth(candidate: tuple, seeds: list[tuple[int, int, int]]) -> int:
    """How deep the best prefix match goes: 3 = same cluster, 0 = unrelated.

    Depth is the whole ranking signal. The RQ-VAE quantises coarse to fine,
    so agreeing on sid_0 alone is a broad category resemblance while
    agreeing on all three means the two products landed in one cluster.
    """
    best = 0
    for seed in seeds:
        depth = 0
        for position in range(3):
            if candidate[position] != seed[position]:
                break
            depth += 1
        best = max(best, depth)
    return best


async def recommend(
    session: AsyncSession, user_id: str, limit: int
) -> tuple[list[dict], str]:
    """Products for the "for you" strip, and which route produced them.

    The reason is returned rather than logged because the client shows it:
    a strip that says why it is there is honest about a cold start instead
    of dressing up the best-seller list as personalisation.
    """
    history = await recent_views(session, user_id)
    seeds = await _semantic_ids(session, history)
    if not seeds:
        return await products.list_popular(session, limit), "popular"

    # One index-backed read: everything sharing a coarse code with anything
    # in the history. Narrowing further in SQL would cost a query per seed
    # for a filter that _match_depth applies anyway.
    result = await session.execute(
        select(Product.id, Product.sid_0, Product.sid_1, Product.sid_2).where(
            Product.status == "ACTIVE",
            Product.id.not_in(history),
            or_(*(Product.sid_0 == seed[0] for seed in seeds)),
        )
    )
    ranked = sorted(
        (
            (_match_depth((a, b, c), seeds), product_id)
            for product_id, a, b, c in result.all()
        ),
        key=lambda scored: (-scored[0], scored[1]),
    )
    picked = [product_id for depth, product_id in ranked if depth > 0][:limit]
    if not picked:
        return await products.list_popular(session, limit), "popular"

    rows = await products.list_by_ids(session, picked)
    # A thin catalogue can leave the strip half empty; best sellers top it
    # up rather than showing three cards next to seven gaps.
    if len(rows) < limit:
        already = [row["product"].id for row in rows] + history
        rows += await products.list_popular(session, limit - len(rows), already)
    return rows, "semantic-id"
