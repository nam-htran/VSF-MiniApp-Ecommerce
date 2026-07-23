"""Product reviews.

  only a buyer who paid for the product may review it
  an unpaid order does not grant the right
  reviews are public, and drive the average and count
  one review per buyer per product — a second rating updates the first
"""

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.payments.security import compute_hash
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


async def seller_with_product(base_url: str) -> str:
    token = await token_for(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": "Shop A", "description": "."},
        )
        product = await client.post(
            f"{base_url}/products",
            headers=auth(token),
            json={"name": "Bàn phím", "description": ".", "price": 690000, "stock": 10},
        )
    return product.json()["id"]


async def place_order(base_url: str, buyer: str, product_id: str) -> tuple[str, int]:
    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": "12 Lê Lợi, Q1",
                    "items": [{"productId": product_id, "qty": 1}],
                },
            )
        ).json()
    return order["id"], int(order["total"])


async def pay(base_url: str, order_id: str, amount: int) -> None:
    body = {
        "paymentId": "p",
        "orderId": order_id,
        "amount": amount,
        "status": "PAID",
        "secureHash": compute_hash(
            settings.payment_ipn_secret, order_id, amount, "PAID"
        ),
    }
    async with httpx.AsyncClient() as client:
        await client.post(f"{base_url}/payments/ipn", json=body)


async def review(base_url, token, product_id, rating, comment=None):
    async with httpx.AsyncClient() as client:
        return await client.post(
            f"{base_url}/products/{product_id}/reviews",
            headers=auth(token),
            json={"rating": rating, "comment": comment},
        )


async def test_only_a_paid_buyer_can_review(base_url):
    product_id = await seller_with_product(base_url)
    buyer = await token_for(base_url, USER_B_ID)
    stranger = await token_for(base_url, USER_C_ID)

    # A stranger who never bought it is refused.
    refused = await review(base_url, stranger, product_id, 5)
    assert refused.status_code == 403

    order_id, amount = await place_order(base_url, buyer, product_id)
    # Order placed but unpaid: still not allowed.
    unpaid = await review(base_url, buyer, product_id, 5)
    assert unpaid.status_code == 403

    await pay(base_url, order_id, amount)
    ok = await review(base_url, buyer, product_id, 5, "Tốt")
    assert ok.status_code == 201
    assert ok.json()["rating"] == 5


async def test_reviews_drive_average_and_count(base_url):
    product_id = await seller_with_product(base_url)
    for user, rating in ((USER_B_ID, 4), (USER_C_ID, 2)):
        buyer = await token_for(base_url, user)
        order_id, amount = await place_order(base_url, buyer, product_id)
        await pay(base_url, order_id, amount)
        await review(base_url, buyer, product_id, rating)

    async with httpx.AsyncClient() as client:
        listing = (
            await client.get(f"{base_url}/products/{product_id}/reviews")
        ).json()
    assert listing["count"] == 2
    assert listing["average"] == 3.0


async def test_one_review_per_buyer_updates_in_place(base_url):
    product_id = await seller_with_product(base_url)
    buyer = await token_for(base_url, USER_B_ID)
    order_id, amount = await place_order(base_url, buyer, product_id)
    await pay(base_url, order_id, amount)

    await review(base_url, buyer, product_id, 5, "Lúc đầu rất thích")
    await review(base_url, buyer, product_id, 3, "Dùng lâu thấy bình thường")

    async with httpx.AsyncClient() as client:
        listing = (
            await client.get(f"{base_url}/products/{product_id}/reviews")
        ).json()
    assert listing["count"] == 1
    assert listing["items"][0]["rating"] == 3
