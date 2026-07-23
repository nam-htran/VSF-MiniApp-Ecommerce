"""Seller fulfilment — the other half of model B.

  a paid order surfaces in its shop's queue; an unpaid one does not
  the seller walks a slice CONFIRMED -> SHIPPING -> DELIVERED, one step at a time
  skipping a step or moving past DELIVERED is refused (409)
  a seller can neither see nor touch another shop's slices (AUTH-05, as 404)
  the status filter narrows the queue
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


ADDRESS = "12 Lê Lợi, Q1, HCM"


async def open_shop(base_url: str, seller: str, name: str) -> str:
    """Open a shop with one product; return the product id."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(seller),
            json={"name": name, "description": "."},
        )
        created = await client.post(
            f"{base_url}/products",
            headers=auth(seller),
            json={"name": f"Hàng {name}", "description": ".", "price": 690000, "stock": 10},
        )
    return created.json()["id"]


async def place_and_pay(base_url: str, buyer: str, product_id: str) -> str:
    """Place an order for one product and settle it via a signed IPN, so it
    reaches the seller's queue as a PAID order."""
    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={"address": ADDRESS, "items": [{"productId": product_id, "qty": 1}]},
            )
        ).json()
        amount = int(order["total"])
        await client.post(
            f"{base_url}/payments/ipn",
            json={
                "paymentId": "pay_test",
                "orderId": order["id"],
                "amount": amount,
                "status": "PAID",
                "secureHash": compute_hash(
                    settings.payment_ipn_secret, order["id"], amount, "PAID"
                ),
            },
        )
    return order["id"]


async def test_only_paid_orders_reach_the_seller_queue(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await open_shop(base_url, seller, "Shop B")

    async with httpx.AsyncClient() as client:
        # An unpaid order: placed but never settled.
        await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={"address": ADDRESS, "items": [{"productId": product, "qty": 1}]},
        )
        before = await client.get(f"{base_url}/orders/shop", headers=auth(seller))
    assert before.json()["items"] == []

    await place_and_pay(base_url, buyer, product)

    async with httpx.AsyncClient() as client:
        after = await client.get(f"{base_url}/orders/shop", headers=auth(seller))
    queue = after.json()["items"]
    assert len(queue) == 1
    assert queue[0]["status"] == "CONFIRMED"
    assert queue[0]["address"] == ADDRESS
    assert queue[0]["items"][0]["qty"] == 1


async def test_seller_walks_a_slice_forward(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await open_shop(base_url, seller, "Shop B")
    await place_and_pay(base_url, buyer, product)

    async with httpx.AsyncClient() as client:
        queue = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller))
        ).json()["items"]
        shop_order_id = queue[0]["id"]

        shipping = await client.patch(
            f"{base_url}/orders/shop/{shop_order_id}",
            headers=auth(seller),
            json={"status": "SHIPPING"},
        )
        delivered = await client.patch(
            f"{base_url}/orders/shop/{shop_order_id}",
            headers=auth(seller),
            json={"status": "DELIVERED"},
        )
        # Already delivered: nothing left to advance to.
        again = await client.patch(
            f"{base_url}/orders/shop/{shop_order_id}",
            headers=auth(seller),
            json={"status": "DELIVERED"},
        )

    assert shipping.status_code == 200 and shipping.json()["status"] == "SHIPPING"
    assert delivered.status_code == 200 and delivered.json()["status"] == "DELIVERED"
    assert again.status_code == 409


async def test_cannot_skip_a_step(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await open_shop(base_url, seller, "Shop B")
    await place_and_pay(base_url, buyer, product)

    async with httpx.AsyncClient() as client:
        queue = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller))
        ).json()["items"]
        # CONFIRMED -> DELIVERED skips SHIPPING.
        jump = await client.patch(
            f"{base_url}/orders/shop/{queue[0]['id']}",
            headers=auth(seller),
            json={"status": "DELIVERED"},
        )
    assert jump.status_code == 409


async def test_a_seller_cannot_touch_another_shops_slice(base_url):
    seller_b = await token_for(base_url, USER_B_ID)
    seller_c = await token_for(base_url, USER_C_ID)
    buyer = await token_for(base_url, USER_A_ID)

    product_b = await open_shop(base_url, seller_b, "Shop B")
    await open_shop(base_url, seller_c, "Shop C")
    await place_and_pay(base_url, buyer, product_b)

    async with httpx.AsyncClient() as client:
        # Seller C's own queue is empty — B's paid order isn't theirs.
        c_queue = await client.get(f"{base_url}/orders/shop", headers=auth(seller_c))

        b_slice = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller_b))
        ).json()["items"][0]["id"]
        # And C cannot advance B's slice: 404, ids stay undiscoverable.
        intruder = await client.patch(
            f"{base_url}/orders/shop/{b_slice}",
            headers=auth(seller_c),
            json={"status": "SHIPPING"},
        )

    assert c_queue.json()["items"] == []
    assert intruder.status_code == 404


async def test_status_filter_narrows_the_queue(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await open_shop(base_url, seller, "Shop B")
    await place_and_pay(base_url, buyer, product)

    async with httpx.AsyncClient() as client:
        slice_id = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller))
        ).json()["items"][0]["id"]
        await client.patch(
            f"{base_url}/orders/shop/{slice_id}",
            headers=auth(seller),
            json={"status": "SHIPPING"},
        )
        shipping = await client.get(
            f"{base_url}/orders/shop?status=SHIPPING", headers=auth(seller)
        )
        confirmed = await client.get(
            f"{base_url}/orders/shop?status=CONFIRMED", headers=auth(seller)
        )

    assert len(shipping.json()["items"]) == 1
    assert confirmed.json()["items"] == []


async def test_seller_endpoint_needs_a_shop(base_url):
    # A logged-in buyer with no shop is a buyer, not a seller: 403.
    buyer = await token_for(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/orders/shop", headers=auth(buyer))
    assert response.status_code == 403
