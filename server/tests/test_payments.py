"""Payment IPN — the merchant side.

  a valid, signed notification flips an order PENDING -> PAID
  a forged signature is rejected (400) and changes nothing
  the amount is checked against the order's own total
  a repeated notification is idempotent — the gateway retries until acked
  verification can be turned off by config
"""

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.payments.security import compute_hash
from tests.conftest import USER_A_ID, USER_B_ID

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


async def place_order(base_url: str) -> tuple[str, int, str]:
    """Open a shop with one product, buy it, return (orderId, total, buyer)."""
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(seller),
            json={"name": "Shop B", "description": "."},
        )
        product = await client.post(
            f"{base_url}/products",
            headers=auth(seller),
            json={"name": "Bàn phím", "description": ".", "price": 690000, "stock": 10},
        )
        order = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={
                "address": "12 Lê Lợi, Q1, HCM",
                "items": [{"productId": product.json()["id"], "qty": 1}],
            },
        )
    body = order.json()
    return body["id"], int(body["total"]), buyer


def ipn_body(order_id: str, amount: int, status: str = "PAID") -> dict:
    return {
        "paymentId": "pay_test",
        "orderId": order_id,
        "amount": amount,
        "status": status,
        "secureHash": compute_hash(
            settings.payment_ipn_secret, order_id, amount, status
        ),
    }


async def order_status(base_url: str, buyer: str, order_id: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/orders/{order_id}", headers=auth(buyer)
        )
    return response.json()["status"]


async def test_valid_ipn_marks_order_paid(base_url):
    order_id, amount, buyer = await place_order(base_url)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/payments/ipn", json=ipn_body(order_id, amount)
        )
    assert response.status_code == 200
    assert await order_status(base_url, buyer, order_id) == "PAID"


async def test_forged_signature_is_rejected(base_url):
    order_id, amount, buyer = await place_order(base_url)
    body = ipn_body(order_id, amount)
    body["secureHash"] = "deadbeef"
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{base_url}/payments/ipn", json=body)
    assert response.status_code == 400
    assert await order_status(base_url, buyer, order_id) == "PENDING"


async def test_amount_mismatch_is_rejected(base_url):
    order_id, amount, buyer = await place_order(base_url)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/payments/ipn", json=ipn_body(order_id, amount - 1000)
        )
    assert response.status_code == 400
    assert await order_status(base_url, buyer, order_id) == "PENDING"


async def test_ipn_is_idempotent(base_url):
    order_id, amount, buyer = await place_order(base_url)
    async with httpx.AsyncClient() as client:
        first = await client.post(
            f"{base_url}/payments/ipn", json=ipn_body(order_id, amount)
        )
        second = await client.post(
            f"{base_url}/payments/ipn", json=ipn_body(order_id, amount)
        )
    assert first.status_code == 200 and second.status_code == 200
    assert await order_status(base_url, buyer, order_id) == "PAID"


async def test_unknown_order_is_404(base_url):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/payments/ipn", json=ipn_body("no-such-order", 1000)
        )
    assert response.status_code == 404


async def test_verification_can_be_disabled(base_url, monkeypatch):
    order_id, amount, buyer = await place_order(base_url)
    monkeypatch.setattr(settings, "payment_verify_hash", False)
    body = ipn_body(order_id, amount)
    body["secureHash"] = "not-even-close"
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{base_url}/payments/ipn", json=body)
    assert response.status_code == 200
    assert await order_status(base_url, buyer, order_id) == "PAID"
