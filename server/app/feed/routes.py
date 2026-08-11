"""HTTP API for reactions and comments on product-feed posts."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, OptionalUser
from app.db import get_session
from app.feed import store as feed
from app.feed.store import FeedComment
from app.products import store as products

router = APIRouter(tags=["Feed"])
Session = Annotated[AsyncSession, Depends(get_session)]


class ReactionRequest(BaseModel):
    reactionType: Literal["LIKE", "LOVE", "HAHA", "WOW", "SAD"] = "LOVE"


class CommentRequest(BaseModel):
    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]


async def _active_product(session: AsyncSession, product_id: str) -> None:
    product = await products.find_by_id(session, product_id)
    if product is None or product.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )


def _comment_view(
    comment: FeedComment, author_name: str | None, current_user_id: str | None
) -> dict:
    return {
        "id": comment.id,
        "content": comment.content,
        "authorName": author_name or "Người dùng V-App",
        "createdAt": comment.created_at.isoformat(),
        "isMine": comment.user_id == current_user_id,
    }


@router.put("/products/{product_id}/reaction")
async def set_reaction(
    product_id: str,
    body: ReactionRequest,
    user: CurrentUser,
    session: Session,
) -> dict:
    await _active_product(session, product_id)
    count = await feed.set_reaction(
        session, product_id, user.id, body.reactionType
    )
    return {
        "reactedByMe": True,
        "reactionType": body.reactionType,
        "reactionCount": count,
    }


@router.delete("/products/{product_id}/reaction")
async def remove_reaction(
    product_id: str, user: CurrentUser, session: Session
) -> dict:
    await _active_product(session, product_id)
    count = await feed.remove_reaction(session, product_id, user.id)
    return {
        "reactedByMe": False,
        "reactionType": None,
        "reactionCount": count,
    }


@router.get("/products/{product_id}/comments")
async def list_comments(
    product_id: str,
    session: Session,
    user: OptionalUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    await _active_product(session, product_id)
    rows = await feed.list_comments(session, product_id, limit, offset)
    count = await feed.comment_count(session, product_id)
    return {
        "items": [
            _comment_view(comment, name, user.id if user else None)
            for comment, name in rows
        ],
        "count": count,
        "hasMore": offset + len(rows) < count,
    }


@router.post(
    "/products/{product_id}/comments", status_code=status.HTTP_201_CREATED
)
async def create_comment(
    product_id: str,
    body: CommentRequest,
    user: CurrentUser,
    session: Session,
) -> dict:
    await _active_product(session, product_id)
    comment = await feed.create_comment(
        session, product_id, user.id, body.content
    )
    return _comment_view(comment, user.name, user.id)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: str, user: CurrentUser, session: Session
) -> Response:
    comment = await feed.find_comment(session, comment_id)
    if comment is None or comment.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    await feed.delete_comment(session, comment)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
