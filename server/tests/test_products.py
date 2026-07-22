"""Products.

The rules under test:
  a seller may only put products in their own shop
  a seller may only edit products in their own shop
  hidden products never reach the storefront
  the shop is taken from the caller, never from the request body
"""

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


async def seller_with_shop(base_url: str, vapp_user_id: str, shop_name: str):
    """Log in and open a shop. Opening the shop is what grants SELLER."""
    token = await token_for(base_url, vapp_user_id)
    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": shop_name, "description": "..."},
        )
    return token, created.json()["id"]


PRODUCT = {"name": "Ấm siêu tốc", "description": "1.8 lít", "price": 350000, "stock": 5}


async def test_seller_adds_a_product_to_their_own_shop(base_url):
    token, shop_id = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )

    assert response.status_code == 201
    body = response.json()
    # The shop is derived from the caller — the request never named one.
    assert body["shopId"] == shop_id
    assert body["price"] == 350000
    assert body["status"] == "ACTIVE"


async def test_buyer_cannot_add_a_product(base_url):
    token = await token_for(base_url, USER_B_ID)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )

    assert response.status_code == 403


async def test_seller_cannot_edit_another_shops_product(base_url):
    token_b, _ = await seller_with_shop(base_url, USER_B_ID, "Shop B")
    token_c, _ = await seller_with_shop(base_url, USER_C_ID, "Shop C")

    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/products", headers=auth(token_b), json=PRODUCT
        )
        product_id = created.json()["id"]

        response = await client.patch(
            f"{base_url}/products/{product_id}",
            headers=auth(token_c),
            json={"price": 1},
        )
        after = await client.get(f"{base_url}/products/{product_id}")

    assert response.status_code == 404
    assert after.json()["price"] == 350000


async def test_hidden_products_stay_out_of_the_storefront(base_url):
    token, shop_id = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )
        product_id = created.json()["id"]

        await client.patch(
            f"{base_url}/products/{product_id}",
            headers=auth(token),
            json={"status": "HIDDEN"},
        )

        storefront = await client.get(f"{base_url}/shops/{shop_id}/products")
        detail = await client.get(f"{base_url}/products/{product_id}")
        mine = await client.get(
            f"{base_url}/products/mine", headers=auth(token)
        )

    assert storefront.json()["items"] == []
    assert detail.status_code == 404
    # The seller still sees it, otherwise they could never unhide it.
    assert [p["id"] for p in mine.json()["items"]] == [product_id]


async def test_negative_stock_is_rejected(base_url):
    token, _ = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/products",
            headers=auth(token),
            json={**PRODUCT, "stock": -1},
        )

    assert response.status_code == 422


async def test_storefront_needs_no_token(base_url):
    token, shop_id = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )
        response = await client.get(f"{base_url}/shops/{shop_id}/products")

    assert response.status_code == 200
    assert [p["name"] for p in response.json()["items"]] == ["Ấm siêu tốc"]
