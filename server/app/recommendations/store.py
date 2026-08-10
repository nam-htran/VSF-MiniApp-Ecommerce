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

When configured, the Transformer generates likely next Semantic IDs. The
prefix matcher remains the fallback and also powers related products.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.products import store as products
from app.products.store import Product
from app.recommendations import predictor

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


async def recent_view_events(
    session: AsyncSession, user_id: str, limit: int = HISTORY_DEPTH
) -> list[str]:
    """Recent views oldest first, with repeats preserved for the model."""
    result = await session.scalars(
        select(ProductView.product_id)
        .where(ProductView.user_id == user_id)
        .order_by(ProductView.viewed_at.desc())
        .limit(limit)
    )
    return list(reversed(result.all()))


async def _semantic_ids(
    session: AsyncSession, product_ids: list[str]
) -> list[tuple[int, int, int]]:
    if not product_ids:
        return []
    result = await session.execute(
        select(Product.id, Product.sid_0, Product.sid_1, Product.sid_2).where(
            Product.id.in_(product_ids),
            Product.sid_0.is_not(None),
            Product.sid_1.is_not(None),
            Product.sid_2.is_not(None),
        )
    )
    by_id = {
        product_id: (a, b, c)
        for product_id, a, b, c in result.all()
    }
    return [by_id[product_id] for product_id in product_ids if product_id in by_id]


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


def _business_order(row: dict) -> tuple:
    return (-row["sold"], -row["ratingAverage"], row["product"].id)


async def _predicted_rows(
    session: AsyncSession,
    predictions: list[predictor.Prediction],
    exclude: list[str],
    limit: int,
) -> list[dict]:
    result = await session.execute(
        select(Product.id, Product.sid_0, Product.sid_1, Product.sid_2).where(
            Product.status == "ACTIVE",
            Product.id.not_in(exclude),
            Product.sid_0.in_(
                {prediction.semantic_id[0] for prediction in predictions}
            ),
        )
    )
    semantic_ids = {
        product_id: (a, b, c)
        for product_id, a, b, c in result.all()
    }
    rows = await products.list_by_ids(session, list(semantic_ids))
    by_id = {row["product"].id: row for row in rows}

    pools = []
    for prediction in predictions:
        pool = [
            by_id[product_id]
            for product_id, semantic_id in semantic_ids.items()
            if semantic_id == prediction.semantic_id and product_id in by_id
        ]
        pools.append(sorted(pool, key=_business_order))

    picked = []
    for pool in pools:
        picked += pool[: limit - len(picked)]
        if len(picked) == limit:
            break
    picked_ids = {row["product"].id for row in picked}

    # The demo catalogue is thin. Only after every exact cluster is short do
    # we widen to a two-code prefix, still respecting beam order.
    if len(picked) < limit:
        level_two = []
        for beam, prediction in enumerate(predictions):
            for product_id, semantic_id in semantic_ids.items():
                if product_id in picked_ids or product_id not in by_id:
                    continue
                if semantic_id[:2] == prediction.semantic_id[:2]:
                    level_two.append((beam, by_id[product_id]))
                    picked_ids.add(product_id)
        level_two.sort(key=lambda item: (item[0], _business_order(item[1])))
        picked += [row for _, row in level_two[: limit - len(picked)]]
    return picked


async def _history_rows(
    session: AsyncSession,
    seeds: list[tuple[int, int, int]],
    exclude: list[str],
    limit: int,
    min_depth: int = 1,
) -> list[dict]:
    if not seeds or limit <= 0:
        return []
    result = await session.execute(
        select(Product.id, Product.sid_0, Product.sid_1, Product.sid_2).where(
            Product.status == "ACTIVE",
            Product.id.not_in(exclude),
            or_(*(Product.sid_0 == seed[0] for seed in seeds)),
        )
    )
    depths = {
        product_id: _match_depth((a, b, c), seeds)
        for product_id, a, b, c in result.all()
    }
    rows = await products.list_by_ids(
        session,
        [product_id for product_id, depth in depths.items() if depth >= min_depth],
    )
    return sorted(
        rows,
        key=lambda row: (
            -depths[row["product"].id],
            _business_order(row),
        ),
    )[:limit]


async def recommend(
    session: AsyncSession, user_id: str, limit: int
) -> tuple[list[dict], str]:
    """Products for the "for you" strip, and which route produced them.

    The reason is returned rather than logged because the client shows it:
    a strip that says why it is there is honest about a cold start instead
    of dressing up the best-seller list as personalisation.
    """
    events = await recent_view_events(session, user_id)
    history = list(dict.fromkeys(reversed(events)))
    model_history = await _semantic_ids(session, events)
    seeds = list(dict.fromkeys(reversed(model_history)))
    if not seeds:
        return await products.list_popular(session, limit), "popular"

    predictions = await predictor.predict(model_history)
    rows = (
        await _predicted_rows(session, predictions, history, limit)
        if predictions
        else []
    )
    source = "transformer" if rows else None

    if len(rows) < limit:
        exclude = history + [row["product"].id for row in rows]
        fallback = await _history_rows(
            session, seeds, exclude, limit - len(rows), min_depth=2
        )
        rows += fallback
        if fallback and source is None:
            source = "semantic-id"
    if len(rows) < limit:
        already = [row["product"].id for row in rows] + history
        rows += await products.list_popular(session, limit - len(rows), already)
    return rows, source or "popular"


async def related(
    session: AsyncSession, product: Product, limit: int
) -> list[dict]:
    if any(
        code is None for code in (product.sid_0, product.sid_1, product.sid_2)
    ):
        return await products.list_popular(session, limit, [product.id])
    seed = (product.sid_0, product.sid_1, product.sid_2)
    rows = await _history_rows(session, [seed], [product.id], limit)
    if len(rows) < limit:
        exclude = [product.id] + [row["product"].id for row in rows]
        rows += await products.list_popular(session, limit - len(rows), exclude)
    return rows
