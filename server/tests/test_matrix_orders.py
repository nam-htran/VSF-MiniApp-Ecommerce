"""Test matrix — Checkout & Order Split, and the money-safety rows.

Named after the IDs in Plan.xlsx › Test scenarios, so a row in the sheet
can be traced to the test that proves it. Rows already covered elsewhere
are cross-referenced rather than duplicated:

  ORD-01/02/03  test_orders.py::test_cart_spanning_two_shops_splits…
  ORD-05        test_orders.py::test_out_of_stock_rejects_the_whole_order
  INV-05        test_orders.py::test_two_buyers_race_for_the_last_unit
  INV-01/03/04  test_inventory_hold.py
  PAY-02/04/05  test_payments.py

What is here is what those files don't cover: replayed checkouts, a client
that lies about money, and a cart whose contents change underneath it.
"""

import asyncio

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


def auth(token: str, key: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    return headers


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


async def shop_with_product(
    base_url: str, seller_id: str, shop: str, price: int, stock: int
) -> tuple[str, str]:
    """Open a shop with one product; return (token, product id)."""
    token = await token_for(base_url, seller_id)
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": shop, "description": "."},
        )
        created = await client.post(
            f"{base_url}/products",
            headers=auth(token),
            json={
                "name": f"Hàng {shop}",
                "description": ".",
                "price": price,
                "stock": stock,
            },
        )
    return token, created.json()["id"]


# --- ORD-04: buyer taps checkout more than once -----------------------------


async def test_ord_04_repeated_checkout_creates_one_order(base_url):
    """Five identical requests with one key must buy once, not five times."""
    _, product = await shop_with_product(base_url, USER_B_ID, "Shop B", 100_000, 20)
    buyer = await token_for(base_url, USER_A_ID)
    payload = {"address": ADDRESS, "items": [{"productId": product, "qty": 2}]}

    async with httpx.AsyncClient() as client:
        responses = [
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer, "checkout-key-1"),
                json=payload,
            )
            for _ in range(5)
        ]
        mine = (await client.get(f"{base_url}/orders", headers=auth(buyer))).json()
        after = (await client.get(f"{base_url}/products/{product}")).json()

    assert all(r.status_code == 201 for r in responses)
    # Same order handed back every time.
    assert len({r.json()["id"] for r in responses}) == 1
    assert len(mine["items"]) == 1
    # And the stock moved once, not five times.
    assert after["stock"] == 18


async def test_ord_04_concurrent_replays_still_create_one_order(base_url):
    """The real race: both requests get past the look-up at once."""
    _, product = await shop_with_product(base_url, USER_B_ID, "Shop B", 100_000, 20)
    buyer = await token_for(base_url, USER_A_ID)
    payload = {"address": ADDRESS, "items": [{"productId": product, "qty": 1}]}

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[
                client.post(
                    f"{base_url}/orders",
                    headers=auth(buyer, "checkout-key-race"),
                    json=payload,
                )
                for _ in range(4)
            ]
        )
        mine = (await client.get(f"{base_url}/orders", headers=auth(buyer))).json()
        after = (await client.get(f"{base_url}/products/{product}")).json()

    assert all(r.status_code == 201 for r in results)
    assert len({r.json()["id"] for r in results}) == 1
    assert len(mine["items"]) == 1
    assert after["stock"] == 19


async def test_ord_04_a_different_key_is_a_different_order(base_url):
    """Idempotency must not swallow a genuine second purchase."""
    _, product = await shop_with_product(base_url, USER_B_ID, "Shop B", 100_000, 20)
    buyer = await token_for(base_url, USER_A_ID)
    payload = {"address": ADDRESS, "items": [{"productId": product, "qty": 1}]}

    async with httpx.AsyncClient() as client:
        first = await client.post(
            f"{base_url}/orders", headers=auth(buyer, "key-a"), json=payload
        )
        second = await client.post(
            f"{base_url}/orders", headers=auth(buyer, "key-b"), json=payload
        )
        bare = await client.post(
            f"{base_url}/orders", headers=auth(buyer), json=payload
        )

    ids = {first.json()["id"], second.json()["id"], bare.json()["id"]}
    assert len(ids) == 3


async def test_ord_04_one_buyers_key_cannot_claim_anothers_order(base_url):
    """Keys are scoped per buyer, so a guessable key leaks nothing."""
    _, product = await shop_with_product(base_url, USER_B_ID, "Shop B", 100_000, 20)
    first_buyer = await token_for(base_url, USER_A_ID)
    second_buyer = await token_for(base_url, USER_C_ID)
    payload = {"address": ADDRESS, "items": [{"productId": product, "qty": 1}]}

    async with httpx.AsyncClient() as client:
        mine = await client.post(
            f"{base_url}/orders", headers=auth(first_buyer, "shared"), json=payload
        )
        theirs = await client.post(
            f"{base_url}/orders", headers=auth(second_buyer, "shared"), json=payload
        )

    # Two buyers, one key string, two separate orders.
    assert mine.json()["id"] != theirs.json()["id"]


# --- ORD-06 / SEC-02: the client does not get to price the order -----------


async def test_ord_06_client_supplied_total_is_ignored(base_url):
    """A tampered request cannot buy cheaply: the server prices it."""
    _, product = await shop_with_product(base_url, USER_B_ID, "Shop B", 500_000, 10)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": ADDRESS,
                    "items": [
                        # Extra fields a hostile client might hope are read.
                        {"productId": product, "qty": 1, "price": 1, "total": 1}
                    ],
                    "total": 1,
                    "discount": 999_999,
                },
            )
        ).json()

    shop_order = order["shopOrders"][0]
    assert shop_order["items"][0]["price"] == 500_000
    assert order["total"] == 500_000 + shop_order["shippingFee"]


# --- CART-05: the catalogue changes while the item sits in a cart ----------


async def test_cart_05_hidden_product_cannot_be_checked_out(base_url):
    seller, product = await shop_with_product(
        base_url, USER_B_ID, "Shop B", 100_000, 10
    )
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{base_url}/products/{product}",
            headers=auth(seller),
            json={"status": "HIDDEN"},
        )
        response = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={"address": ADDRESS, "items": [{"productId": product, "qty": 1}]},
        )
        mine = (await client.get(f"{base_url}/orders", headers=auth(buyer))).json()

    assert response.status_code == 409
    assert mine["items"] == []


async def test_cart_04_price_change_applies_at_checkout(base_url):
    """The order is priced when it is placed, not when the cart was filled."""
    seller, product = await shop_with_product(
        base_url, USER_B_ID, "Shop B", 100_000, 10
    )
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{base_url}/products/{product}",
            headers=auth(seller),
            json={"price": 150_000},
        )
        # The quote checkout previews and the order it places must agree.
        quoted = (
            await client.post(
                f"{base_url}/orders/quote",
                json={"items": [{"productId": product, "qty": 1}]},
            )
        ).json()
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={"address": ADDRESS, "items": [{"productId": product, "qty": 1}]},
            )
        ).json()

    assert quoted["merchandise"] == 150_000
    assert order["shopOrders"][0]["items"][0]["price"] == 150_000
    assert order["total"] == quoted["total"]


# --- CART-02: quantity must be a real quantity ------------------------------


@pytest.mark.parametrize("qty", [0, -1, 100])
async def test_cart_02_bad_quantities_are_rejected(base_url, qty):
    _, product = await shop_with_product(base_url, USER_B_ID, "Shop B", 100_000, 10)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={"address": ADDRESS, "items": [{"productId": product, "qty": qty}]},
        )

    assert response.status_code == 422


# --- SEC-01: one seller cannot read another's slice -------------------------


async def test_sec_01_seller_cannot_read_another_shops_sub_order(base_url):
    seller_b, product_b = await shop_with_product(
        base_url, USER_B_ID, "Shop B", 100_000, 10
    )
    seller_c, _ = await shop_with_product(base_url, USER_C_ID, "Shop C", 100_000, 10)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": ADDRESS,
                    "items": [{"productId": product_b, "qty": 1}],
                },
            )
        ).json()
        slice_id = order["shopOrders"][0]["id"]

        # Shop C's owner tries to move Shop B's delivery along.
        intruder = await client.patch(
            f"{base_url}/orders/shop/{slice_id}",
            headers=auth(seller_c),
            json={"status": "SHIPPING"},
        )
        # And their own queue shows nothing of it.
        queue = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller_c))
        ).json()

    assert intruder.status_code == 404  # not 403 — ids stay undiscoverable
    assert queue["items"] == []
