"""The "for you" strip.

  recommendations need a session — there is nobody to personalise for
  a shopper with no history gets best sellers, and is told so
  a viewed product pulls in others sharing its Semantic ID
  what you just looked at is never recommended back to you
  the closer Semantic ID wins
  a view of a product that does not exist is refused
"""

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.config import settings
from tests.conftest import USER_A_ID, USER_B_ID, _throwaway_engine

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


async def seller_with_products(base_url: str, names: list[str]) -> list[str]:
    token = await token_for(base_url, USER_A_ID)
    ids = []
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": "Shop A", "description": "."},
        )
        for name in names:
            created = await client.post(
                f"{base_url}/products",
                headers=auth(token),
                json={"name": name, "description": ".", "price": 100000, "stock": 10},
            )
            ids.append(created.json()["id"])
    return ids


async def set_semantic_id(product_id: str, sid: tuple[int, int, int]) -> None:
    """Semantic IDs come from the model pipeline, so no endpoint accepts
    one — the seed writes them straight to the row and so does this."""
    engine = _throwaway_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE products SET sid_0 = :a, sid_1 = :b, sid_2 = :c"
                " WHERE id = :id"
            ),
            {"id": product_id, "a": sid[0], "b": sid[1], "c": sid[2]},
        )
    await engine.dispose()


async def recommendations(base_url: str, token: str, limit: int = 10) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/recommendations?limit={limit}", headers=auth(token)
        )
    return response.json()


async def view(base_url: str, token: str, product_id: str) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.post(
            f"{base_url}/products/{product_id}/view", headers=auth(token)
        )


async def test_recommendations_need_a_session(base_url):
    async with httpx.AsyncClient() as client:
        anonymous = await client.get(f"{base_url}/recommendations")
    assert anonymous.status_code == 401


async def test_no_history_falls_back_to_best_sellers(base_url):
    await seller_with_products(base_url, ["Bàn phím", "Chuột"])
    buyer = await token_for(base_url, USER_B_ID)

    body = await recommendations(base_url, buyer)

    # Named honestly: nothing here came from this shopper's behaviour.
    assert body["source"] == "popular"
    assert len(body["items"]) == 2


async def test_a_view_pulls_in_products_sharing_its_semantic_id(base_url):
    seen, sibling, stranger = await seller_with_products(
        base_url, ["Ibuprofen 400", "Ibuprofen 600", "Bàn phím cơ"]
    )
    await set_semantic_id(seen, (7, 7, 7))
    await set_semantic_id(sibling, (7, 7, 7))
    await set_semantic_id(stranger, (200, 1, 1))
    buyer = await token_for(base_url, USER_B_ID)

    assert (await view(base_url, buyer, seen)).status_code == 204
    body = await recommendations(base_url, buyer)

    assert body["source"] == "semantic-id"
    returned = [item["id"] for item in body["items"]]
    # The sibling leads: it shares all three codes. The unrelated product
    # may still appear behind it as filler, but never ahead.
    assert returned[0] == sibling
    # And what they just looked at is not recommended back to them.
    assert seen not in returned


async def test_a_closer_semantic_id_ranks_higher(base_url):
    seen, near, far = await seller_with_products(
        base_url, ["Đã xem", "Cùng cụm", "Cùng nhánh"]
    )
    await set_semantic_id(seen, (9, 9, 9))
    # Same three codes — one cluster.
    await set_semantic_id(near, (9, 9, 9))
    # Shares only the coarse code, so a broad resemblance and no more.
    await set_semantic_id(far, (9, 200, 200))
    buyer = await token_for(base_url, USER_B_ID)

    await view(base_url, buyer, seen)
    body = await recommendations(base_url, buyer)

    assert [item["id"] for item in body["items"]][:2] == [near, far]


async def test_viewing_a_product_that_does_not_exist_is_refused(base_url):
    buyer = await token_for(base_url, USER_B_ID)
    missing = await view(base_url, buyer, "00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
