"""Recommendations, and the browsing history they run on."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.db import get_session
from app.products import store as products
# The storefront card's shape lives with the products routes. Imported
# rather than repeated: two copies of a serialiser drift, and the client
# reads both endpoints into the same type.
from app.products.routes import _list_item
from app.recommendations import store as recommendations
from app.vouchers import store as vouchers

router = APIRouter(tags=["Recommendations"])

Session = Annotated[AsyncSession, Depends(get_session)]


def _items(rows: list[dict], live: list, options: dict) -> list[dict]:
    return [_list_item(row, live, options) for row in rows]


@router.post("/products/{product_id}/view", status_code=status.HTTP_204_NO_CONTENT)
async def record_view(
    product_id: str, session: Session, user: CurrentUser
) -> None:
    """Remember that this shopper opened this product.

    Its own endpoint rather than a side effect of GET /products/{id}: a
    prefetch, a crawler, or the seller checking their own listing would all
    count as interest otherwise, and the history feeding the recommender
    would describe nobody.
    """
    product = await products.find_by_id(session, product_id)
    if product is None or product.status == "ARCHIVED":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    await recommendations.record_view(session, user.id, product_id)


@router.get("/recommendations")
async def list_recommendations(
    session: Session,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> dict:
    """The "for you" strip. Signed-in only — without a shopper there is no
    history, and a strip built from nobody's behaviour is just a second
    product grid.

    A signed-in shopper who has looked at nothing still gets an answer, from
    best sellers. `source` says which route produced it, so the strip can
    label itself honestly rather than calling a popularity list
    personalisation.
    """
    rows, source = await recommendations.recommend(session, user.id, limit)
    live = await vouchers.list_live(session)
    options = await products.variants_for(
        session, [row["product"].id for row in rows]
    )
    return {
        "items": _items(rows, live, options),
        "source": source,
    }


@router.get("/products/{product_id}/related")
async def list_related_products(
    product_id: str,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> dict:
    product = await products.find_by_id(session, product_id)
    if product is None or product.status == "ARCHIVED":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    rows = await recommendations.related(session, product, limit)
    live = await vouchers.list_live(session)
    options = await products.variants_for(
        session, [row["product"].id for row in rows]
    )
    return {"items": _items(rows, live, options)}
