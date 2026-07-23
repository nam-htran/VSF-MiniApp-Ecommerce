"""Reading and writing product reviews.

Anyone may read them; only a buyer who paid for the product may write one,
and only their own. The purchase check is the gate — a rating with no
receipt behind it never gets created.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.db import get_session
from app.products import store as products
from app.reviews import store as reviews
from app.reviews.store import Review

router = APIRouter(tags=["Reviews"])

Session = Annotated[AsyncSession, Depends(get_session)]


class ReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


def _serialise(review: Review, reviewer_name: str | None) -> dict:
    return {
        "id": review.id,
        "rating": review.rating,
        "comment": review.comment,
        "reviewerName": reviewer_name or "Người dùng V-App",
        "createdAt": review.created_at.isoformat(),
    }


@router.get("/products/{product_id}/reviews")
async def list_reviews(
    product_id: str,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Public: the reviews and their average, for the product page."""
    rows = await reviews.list_for_product(session, product_id, limit, offset)
    average, count = await reviews.summary(session, product_id)
    return {
        "items": [_serialise(review, name) for review, name in rows],
        "average": average,
        "count": count,
        "hasMore": len(rows) == limit,
    }


@router.post(
    "/products/{product_id}/reviews", status_code=status.HTTP_201_CREATED
)
async def write_review(
    product_id: str, body: ReviewRequest, user: CurrentUser, session: Session
) -> dict:
    product = await products.find_by_id(session, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    if not await reviews.has_purchased(session, user.id, product_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ người đã mua sản phẩm mới đánh giá được",
        )
    review = await reviews.upsert(
        session, product_id, user.id, body.rating, body.comment
    )
    return _serialise(review, user.name)


@router.get("/products/{product_id}/reviews/eligibility")
async def review_eligibility(
    product_id: str, user: CurrentUser, session: Session
) -> dict:
    """Tells the product page whether to show the write-review form, and the
    caller's own review if they already left one."""
    mine = await reviews.find_by_user(session, product_id, user.id)
    return {
        "canReview": await reviews.has_purchased(session, user.id, product_id),
        "myReview": _serialise(mine, user.name) if mine else None,
    }
