"""Persistent reactions and comments on product-feed posts."""

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from tests.conftest import USER_A_ID, USER_B_ID, USER_C_ID

pytestmark = pytest.mark.skipif(
    "127.0.0.1" not in settings.vapp_base_url
    and "localhost" not in settings.vapp_base_url,
    reason="Needs the mock to mint authCodes on demand",
)


@pytest_asyncio.fixture(autouse=True)
async def _empty(clean_db):
    yield


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def token_for(base_url: str, vapp_user_id: str) -> str:
    async with httpx.AsyncClient() as client:
        issued = await client.post(
            f"{settings.vapp_base_url}/simulator/authcode",
            json={"user_id": vapp_user_id, "scopes": "profile phone"},
        )
        session = await client.post(
            f"{base_url}/auth/session",
            json={"authCode": issued.json()["data"]["authCode"]},
        )
    return session.json()["token"]


async def product_for_feed(base_url: str) -> str:
    seller = await token_for(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(seller),
            json={"name": "Shop Feed", "description": "."},
        )
        product = await client.post(
            f"{base_url}/products",
            headers=auth(seller),
            json={
                "name": "Sản phẩm Feed",
                "description": "Bài đăng thử nghiệm",
                "price": 120000,
                "stock": 10,
            },
        )
    return product.json()["id"]


async def marketplace_item(base_url: str, token: str | None = None) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/products?limit=10",
            headers=auth(token) if token else None,
        )
    return response.json()["items"][0]


async def test_reaction_is_idempotent_and_visible_in_marketplace(base_url):
    product_id = await product_for_feed(base_url)
    buyer = await token_for(base_url, USER_B_ID)

    guest_view = await marketplace_item(base_url)
    assert guest_view["reactionCount"] == 0
    assert guest_view["reactedByMe"] is False

    async with httpx.AsyncClient() as client:
        first = await client.put(
            f"{base_url}/products/{product_id}/reaction",
            headers=auth(buyer),
            json={"reactionType": "LOVE"},
        )
        second = await client.put(
            f"{base_url}/products/{product_id}/reaction",
            headers=auth(buyer),
            json={"reactionType": "WOW"},
        )
    assert first.status_code == 200
    assert first.json()["reactionCount"] == 1
    assert second.json()["reactionCount"] == 1
    assert second.json()["reactionType"] == "WOW"

    mine = await marketplace_item(base_url, buyer)
    assert mine["reactionCount"] == 1
    assert mine["reactedByMe"] is True
    assert mine["reactionType"] == "WOW"

    guest_view = await marketplace_item(base_url)
    assert guest_view["reactionCount"] == 1
    assert guest_view["reactedByMe"] is False

    async with httpx.AsyncClient() as client:
        removed = await client.delete(
            f"{base_url}/products/{product_id}/reaction",
            headers=auth(buyer),
        )
    assert removed.json()["reactionCount"] == 0
    assert removed.json()["reactedByMe"] is False


async def test_comments_are_public_but_writes_require_the_owner(base_url):
    product_id = await product_for_feed(base_url)
    buyer = await token_for(base_url, USER_B_ID)
    stranger = await token_for(base_url, USER_C_ID)

    async with httpx.AsyncClient() as client:
        refused = await client.post(
            f"{base_url}/products/{product_id}/comments",
            json={"content": "Không có token"},
        )
        created = await client.post(
            f"{base_url}/products/{product_id}/comments",
            headers=auth(buyer),
            json={"content": "  Sản phẩm rất ổn  "},
        )
    assert refused.status_code == 401
    assert created.status_code == 201
    comment_id = created.json()["id"]
    assert created.json()["content"] == "Sản phẩm rất ổn"
    assert created.json()["isMine"] is True

    async with httpx.AsyncClient() as client:
        public = await client.get(
            f"{base_url}/products/{product_id}/comments"
        )
        mine = await client.get(
            f"{base_url}/products/{product_id}/comments", headers=auth(buyer)
        )
        not_owner = await client.delete(
            f"{base_url}/comments/{comment_id}", headers=auth(stranger)
        )
        deleted = await client.delete(
            f"{base_url}/comments/{comment_id}", headers=auth(buyer)
        )
        empty = await client.get(
            f"{base_url}/products/{product_id}/comments"
        )

    assert public.json()["count"] == 1
    assert public.json()["items"][0]["isMine"] is False
    assert mine.json()["items"][0]["isMine"] is True
    assert not_owner.status_code == 404
    assert deleted.status_code == 204
    assert empty.json()["count"] == 0
