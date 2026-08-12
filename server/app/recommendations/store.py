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

import math
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

# Held across the pages of one storefront walk: a ranking recomputed per
# page would shift under the walk and a product could arrive twice or not
# at all. Only shoppers with history get an entry — everyone else is served
# the shop window, which needs no ranking to be stable.
_rankings: dict[str, tuple[list[str], str]] = {}

# The same, for visitors with no account to key on. One slot rather than a
# table: a walk sends the same history with every page, so holding the last
# answer computes it once per walk, and nothing accumulates. Interleaved
# visitors evict each other and simply recompute — the ranking is a pure
# function of what the request carried, so a miss costs time and never
# correctness.
#
# Staleness is bounded by what a ranking is: an order, not a result set.
# Which products exist comes from SQL on every request either way.
_last_anonymous: tuple[tuple[str, ...], list[str] | None, str | None] | None = None


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
    _rankings.pop(user_id, None)


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


def _diversified_rows(
    rows: list[dict],
    semantic_ids: dict[str, tuple[int, int, int]],
    predictions: list[predictor.Prediction],
    limit: int,
) -> list[dict]:
    """Rerank model recall without prescribing how many items each SID gets.

    The Transformer and prefix depth provide the relevance score. Every item
    already selected adds a small penalty to candidates which repeat its
    coarse branch, two-code branch, or exact cluster. The penalty grows with
    repetition, so a strong cluster can still contribute several products,
    but it cannot occupy the whole first screen merely because it is large.
    """
    if not rows or not predictions or limit <= 0:
        return []

    top_prediction_score = max(prediction.score for prediction in predictions)
    relevance: dict[str, float] = {}
    for row in rows:
        product_id = row["product"].id
        semantic_id = semantic_ids[product_id]
        best = 0.0
        for prediction in predictions:
            depth = _match_depth(semantic_id, [prediction.semantic_id])
            if depth == 0:
                continue
            # Generation returns log-like scores. Relative exponentiation
            # preserves their confidence gaps without depending on the
            # absolute score scale used by a checkpoint.
            model_score = 0.5 + 0.5 * math.exp(
                prediction.score - top_prediction_score
            )
            semantic_score = (0.0, 0.15, 0.55, 1.0)[depth]
            best = max(best, model_score + semantic_score)
        relevance[product_id] = best

    business_rows = sorted(rows, key=_business_order)
    denominator = max(len(business_rows) - 1, 1)
    business_score = {
        row["product"].id: 1.0 - rank / denominator
        for rank, row in enumerate(business_rows)
    }

    # Stable business ordering is also the tiebreak for equal rerank scores.
    remaining = sorted(rows, key=_business_order)
    picked: list[dict] = []
    level_one: dict[int, int] = {}
    level_two: dict[tuple[int, int], int] = {}
    exact: dict[tuple[int, int, int], int] = {}
    while remaining and len(picked) < limit:

        def score(row: dict) -> float:
            product_id = row["product"].id
            sid = semantic_ids[product_id]
            repetition_penalty = (
                0.08 * level_one.get(sid[0], 0)
                + 0.25 * level_two.get(sid[:2], 0)
                + 0.70 * exact.get(sid, 0)
            )
            return (
                relevance[product_id]
                + 0.08 * business_score[product_id]
                - repetition_penalty
            )

        chosen = max(remaining, key=score)
        remaining.remove(chosen)
        picked.append(chosen)
        sid = semantic_ids[chosen["product"].id]
        level_one[sid[0]] = level_one.get(sid[0], 0) + 1
        level_two[sid[:2]] = level_two.get(sid[:2], 0) + 1
        exact[sid] = exact.get(sid, 0) + 1
    return picked


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

    return _diversified_rows(
        list(by_id.values()), semantic_ids, predictions, limit
    )


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
    """Products for a signed-in shopper, and which route produced them."""
    return await recommend_from(
        session, await recent_view_events(session, user_id), limit
    )


async def recommend_from(
    session: AsyncSession, events: list[str], limit: int
) -> tuple[list[dict], str]:
    """The ranking itself, given a browsing history from anywhere.

    Signed in, that history is the product_views table. Signed out it is
    whatever the shopper's own device kept and sent, because a marketplace
    that only recommends to people with accounts recommends to almost
    nobody. Same routes either way — where the sequence came from changes
    nothing about how it is read.

    `events` is oldest first and keeps repeats: the model was trained on
    sessions, and looking at one product four times says something a
    deduplicated list would lose.

    Only what the Semantic IDs actually reach is returned — a few dozen
    products, however large the catalogue. Everything else is left out
    rather than padded with best sellers: the listing query already orders
    what this does not name, by the same units-sold measure and with a
    rating tiebreak this had no way to apply. Padding meant building the
    whole catalogue in Python to arrive at an order SQL was going to
    produce anyway.
    """
    history = list(dict.fromkeys(reversed(events)))
    model_history = await _semantic_ids(session, events)
    seeds = list(dict.fromkeys(reversed(model_history)))
    if not seeds:
        return [], "popular"

    predictions = await predictor.predict(model_history)
    rows = (
        await _predicted_rows(session, predictions, history, limit)
        if predictions
        else []
    )
    source = "transformer" if rows else None

    if len(rows) < limit:
        # All three levels, deepest first — _history_rows sorts by how much
        # of the prefix matches. Sharing only the coarse code is a broad
        # category resemblance and a weak signal, but it is still a signal
        # about this shopper, which is more than the units-sold order it
        # would otherwise fall to.
        exclude = history + [row["product"].id for row in rows]
        fallback = await _history_rows(
            session, seeds, exclude, limit - len(rows), min_depth=1
        )
        rows += fallback
        if fallback and source is None:
            source = "semantic-id"
    return rows, source or "popular"


async def ranked_product_ids(
    session: AsyncSession, user_id: str
) -> tuple[list[str] | None, str]:
    """recommend()'s order as ids the product listing can sort by, and which
    route produced it.

    The route travels with the ranking because nothing else can show it. Once
    recommendations are an order rather than a labelled strip, a Transformer
    answer and a best-seller fallback look identical on screen.

    No ranking at all for a shopper who has looked at nothing: the listing's
    own shop window is already the best-seller order, so ordering by a copy
    of it would cost a walk of the catalogue to change nothing.
    """
    cached = _rankings.get(user_id)
    if cached is not None:
        return cached

    if not await _semantic_ids(session, await recent_view_events(session, user_id)):
        return None, "popular"

    # Bounded by the catalogue rather than by a cut-off chosen by hand. The
    # Semantic IDs stop well short of it either way.
    rows, source = await recommend(
        session, user_id, await products.count_active(session)
    )
    ranking = ([row["product"].id for row in rows] or None, source)
    _rankings[user_id] = ranking
    return ranking


async def ranked_for_seen(
    session: AsyncSession, seen: list[str]
) -> tuple[list[str] | None, str | None]:
    """The same ranking for a shopper with no account, from the history their
    own device kept and sent.

    Held for the length of a walk, like the signed-in one, so the Transformer
    runs once per storefront load rather than once per page as the shopper
    scrolls.

    Nothing is stored, though: a visitor without an account leaves no
    browsing record on the server, and their history stays theirs to clear.
    """
    global _last_anonymous
    key = tuple(seen)
    if _last_anonymous is not None and _last_anonymous[0] == key:
        return _last_anonymous[1], _last_anonymous[2]

    if not seen or not await _semantic_ids(session, seen):
        ranking: list[str] | None = None
        source: str | None = None
    else:
        rows, source = await recommend_from(
            session, seen, await products.count_active(session)
        )
        ranking = [row["product"].id for row in rows] or None

    _last_anonymous = (key, ranking, source)
    return ranking, source


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
