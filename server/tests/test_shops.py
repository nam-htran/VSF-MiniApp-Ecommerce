"""Shop management.

Covers four cases from the test matrix:
  PROD-01  a seller creates a shop with valid data
  PROD-02  a second shop for the same seller is rejected
  AUTH-04  a buyer calling a seller endpoint is rejected
  AUTH-05  a seller reaching another seller's shop is rejected
"""

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from tests.conftest import BUYER_ID, SELLER_A_ID, SELLER_B_ID

pytestmark = pytest.mark.skipif(
    "127.0.0.1" not in settings.vapp_base_url
    and "localhost" not in settings.vapp_base_url,
    reason="Needs the mock to mint authCodes on demand",
)


@pytest_asyncio.fixture(autouse=True)
async def _empty(clean_db):
    yield


async def token_for(base_url: str, vapp_user_id: str) -> str:
    """Log a seed account in and return its V-Market JWT."""
    async with httpx.AsyncClient() as client:
        issued = await client.post(
            f"{settings.vapp_base_url}/simulator/authcode",
            json={"user_id": vapp_user_id, "scopes": "profile phone"},
        )
        auth_code = issued.json()["data"]["authCode"]

        session = await client.post(
            f"{base_url}/auth/session", json={"authCode": auth_code}
        )
    return session.json()["token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_seller_creates_a_shop(base_url):
    token = await token_for(base_url, SELLER_A_ID)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": "Shop A", "description": "Đồ điện tử"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Shop A"
    assert body["status"] == "ACTIVE"


async def test_second_shop_for_same_seller_is_rejected(base_url):
    token = await token_for(base_url, SELLER_A_ID)
    payload = {"name": "Shop A", "description": "Đồ điện tử"}

    async with httpx.AsyncClient() as client:
        first = await client.post(
            f"{base_url}/shops", headers=auth(token), json=payload
        )
        second = await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": "Shop A2", "description": "Thêm cái nữa"},
        )

    assert first.status_code == 201
    assert second.status_code == 409


async def test_buyer_cannot_create_a_shop(base_url):
    token = await token_for(base_url, BUYER_ID)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": "Của người mua", "description": "Không được phép"},
        )

    assert response.status_code == 403


async def test_seller_cannot_edit_another_sellers_shop(base_url):
    token_a = await token_for(base_url, SELLER_A_ID)
    token_b = await token_for(base_url, SELLER_B_ID)

    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/shops",
            headers=auth(token_a),
            json={"name": "Shop A", "description": "Của A"},
        )
        shop_id = created.json()["id"]

        # B knows A's shop id and tries to rename it.
        response = await client.patch(
            f"{base_url}/shops/{shop_id}",
            headers=auth(token_b),
            json={"name": "Đã bị B chiếm"},
        )

        # And the shop must be untouched afterwards.
        after = await client.get(f"{base_url}/shops/{shop_id}")

    assert response.status_code == 404
    assert after.json()["name"] == "Shop A"


async def test_request_without_a_token_is_rejected(base_url):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/shops",
            json={"name": "Ẩn danh", "description": "Không có token"},
        )

    assert response.status_code == 401


async def test_seller_edits_own_shop(base_url):
    token = await token_for(base_url, SELLER_A_ID)

    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": "Shop A", "description": "Mô tả cũ"},
        )
        shop_id = created.json()["id"]

        updated = await client.patch(
            f"{base_url}/shops/{shop_id}",
            headers=auth(token),
            json={"description": "Mô tả mới"},
        )
        mine = await client.get(f"{base_url}/shops/me", headers=auth(token))

    assert updated.json()["description"] == "Mô tả mới"
    # A partial update must not blank the fields it did not mention.
    assert updated.json()["name"] == "Shop A"
    assert mine.json()["id"] == shop_id
