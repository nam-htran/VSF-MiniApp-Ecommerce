"""Test matrix — the rows that describe behaviour already built.

Named after the IDs in Plan.xlsx › Test scenarios. Nothing here needed a
new feature; these are the guarantees the system already makes but nobody
had pinned down.

  AUTH-06  an expired token is refused
  CART-06  the basket total is the sum of its lines, to the đồng
  INV-02   paying makes the hold permanent
  INV-06   the sweep and a payment racing: one wins, cleanly
  INV-07   a seller editing stock mid-checkout breaks no invariant
  PAY-06   a late callback after the status was read stays consistent
  STATE-06 two shops on one order move independently
  SEC-04   a checkout that fails leaves nothing half-written
  E2E-01   one shop, end to end
  E2E-02   two shops in one checkout, each seller handling their own
  E2E-03   payment abandoned: the buyer sees it and the stock returns
"""

import asyncio

import httpx
import jwt
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


ADDRESS = "12 Lê Lợi, Q1, HCM"


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


async def open_shop(
    base_url: str, seller_id: str, name: str, price: int, stock: int
) -> tuple[str, str]:
    token = await token_for(base_url, seller_id)
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": name, "description": "."},
        )
        created = await client.post(
            f"{base_url}/products",
            headers=auth(token),
            json={
                "name": f"Hàng {name}",
                "description": ".",
                "price": price,
                "stock": stock,
            },
        )
    return token, created.json()["id"]


async def pay(client: httpx.AsyncClient, base_url: str, order: dict) -> httpx.Response:
    amount = int(order["total"])
    return await client.post(
        f"{base_url}/payments/ipn",
        json={
            "paymentId": f"pay_{order['id'][:8]}",
            "orderId": order["id"],
            "amount": amount,
            "status": "PAID",
            "secureHash": compute_hash(
                settings.payment_ipn_secret, order["id"], amount, "PAID"
            ),
        },
    )


# --- AUTH-06 ---------------------------------------------------------------


async def test_auth_06_expired_token_is_refused(base_url):
    """A token past its exp must not open anything, however well formed."""
    live = await token_for(base_url, USER_A_ID)
    claims = jwt.decode(live, options={"verify_signature": False})
    # Same signature key, same subject — only the clock has moved on.
    expired = jwt.encode(
        {**claims, "exp": claims["exp"] - settings.jwt_ttl_seconds - 60},
        settings.jwt_secret,
        algorithm="HS256",
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/orders", headers=auth(expired))
        # And browsing still works without any token at all.
        public = await client.get(f"{base_url}/products")

    assert response.status_code == 401
    assert public.status_code == 200


# --- CART-06 ---------------------------------------------------------------


async def test_cart_06_total_is_the_sum_of_its_lines(base_url):
    """Money is Numeric end to end; a basket of odd prices must not drift."""
    _, first = await open_shop(base_url, USER_B_ID, "Shop B", 33_333, 50)
    _, second = await open_shop(base_url, USER_C_ID, "Shop C", 16_667, 50)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": ADDRESS,
                    "items": [
                        {"productId": first, "qty": 3},
                        {"productId": second, "qty": 7},
                    ],
                },
            )
        ).json()

    lines = sum(
        item["price"] * item["qty"]
        for shop_order in order["shopOrders"]
        for item in shop_order["items"]
    )
    fees = sum(shop["shippingFee"] for shop in order["shopOrders"])
    assert lines == 33_333 * 3 + 16_667 * 7
    assert order["total"] == lines + fees
    # Each shop's subtotal is its own lines, exactly.
    for shop_order in order["shopOrders"]:
        assert shop_order["subtotal"] == sum(
            item["price"] * item["qty"] for item in shop_order["items"]
        )


# --- INV-02 ----------------------------------------------------------------


async def test_inv_02_paying_makes_the_hold_permanent(base_url, monkeypatch):
    _, product = await open_shop(base_url, USER_B_ID, "Shop B", 100_000, 10)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={"address": ADDRESS, "items": [{"productId": product, "qty": 4}]},
            )
        ).json()
        await pay(client, base_url, order)

        # Even with the hold window at zero, a paid order keeps its stock.
        monkeypatch.setattr(settings, "order_hold_minutes", 0)
        await client.get(f"{base_url}/orders", headers=auth(buyer))
        after = (await client.get(f"{base_url}/products/{product}")).json()
        listed = (
            await client.get(f"{base_url}/orders", headers=auth(buyer))
        ).json()["items"][0]

    assert after["stock"] == 6
    assert listed["status"] == "PAID"
    # Sold is counted from paid orders, so it moved too.


# --- INV-06 ----------------------------------------------------------------


async def test_inv_06_sweep_and_payment_racing_leave_one_outcome(
    base_url, monkeypatch
):
    """The expiry sweep and a payment arriving together must not both win:
    an order cannot end up paid *and* have its stock returned."""
    _, product = await open_shop(base_url, USER_B_ID, "Shop B", 100_000, 10)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={"address": ADDRESS, "items": [{"productId": product, "qty": 3}]},
            )
        ).json()

        monkeypatch.setattr(settings, "order_hold_minutes", 0)
        # Fire both at once: the sweep runs inside the orders listing.
        await asyncio.gather(
            client.get(f"{base_url}/orders", headers=auth(buyer)),
            pay(client, base_url, order),
        )

        final = (
            await client.get(f"{base_url}/orders/{order['id']}", headers=auth(buyer))
        ).json()
        after = (await client.get(f"{base_url}/products/{product}")).json()

    # Exactly one of the two outcomes, and the stock matches it.
    assert final["status"] in {"PAID", "CANCELLED"}
    assert after["stock"] == (7 if final["status"] == "PAID" else 10)


# --- INV-07 ----------------------------------------------------------------


async def test_inv_07_seller_editing_stock_breaks_no_invariant(base_url):
    """A seller may set stock to anything ≥ 0 at any time; what must never
    happen is a sale of stock that isn't there."""
    seller, product = await open_shop(base_url, USER_B_ID, "Shop B", 100_000, 10)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        # Seller cuts stock to 1 while the buyer is deciding.
        await client.patch(
            f"{base_url}/products/{product}",
            headers=auth(seller),
            json={"stock": 1},
        )
        too_many = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={"address": ADDRESS, "items": [{"productId": product, "qty": 3}]},
        )
        just_enough = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={"address": ADDRESS, "items": [{"productId": product, "qty": 1}]},
        )
        after = (await client.get(f"{base_url}/products/{product}")).json()
        negative = await client.patch(
            f"{base_url}/products/{product}",
            headers=auth(seller),
            json={"stock": -5},
        )

    assert too_many.status_code == 409
    assert just_enough.status_code == 201
    assert after["stock"] == 0
    assert negative.status_code == 422  # never below zero


# --- PAY-06 ----------------------------------------------------------------


async def test_pay_06_late_callback_after_reading_status(base_url):
    """Reading the order first, then the callback landing, must end in one
    consistent state — and a duplicate late callback changes nothing."""
    _, product = await open_shop(base_url, USER_B_ID, "Shop B", 100_000, 10)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={"address": ADDRESS, "items": [{"productId": product, "qty": 1}]},
            )
        ).json()

        early = (
            await client.get(f"{base_url}/orders/{order['id']}", headers=auth(buyer))
        ).json()
        first = await pay(client, base_url, order)
        late = await pay(client, base_url, order)
        final = (
            await client.get(f"{base_url}/orders/{order['id']}", headers=auth(buyer))
        ).json()
        after = (await client.get(f"{base_url}/products/{product}")).json()

    assert early["status"] == "PENDING"
    assert first.status_code == 200 and late.status_code == 200
    assert final["status"] == "PAID"
    # The late one did not take a second unit.
    assert after["stock"] == 9


# --- STATE-06 --------------------------------------------------------------


async def test_state_06_two_shops_move_independently(base_url):
    seller_b, product_b = await open_shop(base_url, USER_B_ID, "Shop B", 100_000, 10)
    seller_c, product_c = await open_shop(base_url, USER_C_ID, "Shop C", 200_000, 10)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": ADDRESS,
                    "items": [
                        {"productId": product_b, "qty": 1},
                        {"productId": product_c, "qty": 1},
                    ],
                },
            )
        ).json()
        await pay(client, base_url, order)

        # Shop B ships and delivers; shop C does nothing.
        queue = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller_b))
        ).json()["items"]
        for step in ("SHIPPING", "DELIVERED"):
            await client.patch(
                f"{base_url}/orders/shop/{queue[0]['id']}",
                headers=auth(seller_b),
                json={"status": step},
            )

        seen = (
            await client.get(f"{base_url}/orders/{order['id']}", headers=auth(buyer))
        ).json()
        c_queue = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller_c))
        ).json()["items"]

    states = {s["shopName"]: s["status"] for s in seen["shopOrders"]}
    assert states["Shop B"] == "DELIVERED"
    assert states["Shop C"] == "CONFIRMED"
    assert c_queue[0]["status"] == "CONFIRMED"


# --- SEC-04 ----------------------------------------------------------------


async def test_sec_04_a_failed_checkout_leaves_nothing_behind(base_url):
    """One transaction: if any line fails, no order, no stock movement, no
    half-written shop order."""
    _, plenty = await open_shop(base_url, USER_B_ID, "Shop B", 100_000, 10)
    _, scarce = await open_shop(base_url, USER_C_ID, "Shop C", 100_000, 1)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        failed = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={
                "address": ADDRESS,
                "items": [
                    {"productId": plenty, "qty": 2},
                    {"productId": scarce, "qty": 5},  # not enough
                ],
            },
        )
        mine = (await client.get(f"{base_url}/orders", headers=auth(buyer))).json()
        left = (await client.get(f"{base_url}/products/{plenty}")).json()
        right = (await client.get(f"{base_url}/products/{scarce}")).json()

    assert failed.status_code == 409
    assert mine["items"] == []          # no order at all
    assert left["stock"] == 10          # the good line was not taken either
    assert right["stock"] == 1


# --- E2E-01 / E2E-02 / E2E-03 ---------------------------------------------


async def test_e2e_01_single_shop_purchase(base_url):
    """List → buy → pay → seller ships → delivered."""
    seller, product = await open_shop(base_url, USER_B_ID, "Shop B", 250_000, 5)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        storefront = (await client.get(f"{base_url}/products")).json()
        assert any(p["id"] == product for p in storefront["items"])

        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={"address": ADDRESS, "items": [{"productId": product, "qty": 2}]},
            )
        ).json()
        await pay(client, base_url, order)

        slice_id = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller))
        ).json()["items"][0]["id"]
        for step in ("SHIPPING", "DELIVERED"):
            await client.patch(
                f"{base_url}/orders/shop/{slice_id}",
                headers=auth(seller),
                json={"status": step},
            )

        final = (
            await client.get(f"{base_url}/orders/{order['id']}", headers=auth(buyer))
        ).json()
        after = (await client.get(f"{base_url}/products/{product}")).json()
        listed = next(
            p
            for p in (await client.get(f"{base_url}/products")).json()["items"]
            if p["id"] == product
        )
        # Having bought and paid, the buyer may now review it.
        review = await client.post(
            f"{base_url}/products/{product}/reviews",
            headers=auth(buyer),
            json={"rating": 5, "comment": "Giao nhanh, đóng gói kỹ."},
        )

    assert final["status"] == "PAID"
    assert final["shopOrders"][0]["status"] == "DELIVERED"
    assert after["stock"] == 3
    assert listed["sold"] == 2
    assert review.status_code == 201


async def test_e2e_02_two_shops_each_seller_handles_their_own(base_url):
    seller_b, product_b = await open_shop(base_url, USER_B_ID, "Shop B", 100_000, 5)
    seller_c, product_c = await open_shop(base_url, USER_C_ID, "Shop C", 300_000, 5)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": ADDRESS,
                    "items": [
                        {"productId": product_b, "qty": 1},
                        {"productId": product_c, "qty": 2},
                    ],
                },
            )
        ).json()
        await pay(client, base_url, order)

        b_queue = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller_b))
        ).json()["items"]
        c_queue = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller_c))
        ).json()["items"]

    # One payment, two deliveries — and each seller sees only their own.
    assert len(order["shopOrders"]) == 2
    assert len(b_queue) == 1 and len(c_queue) == 1
    assert b_queue[0]["items"][0]["productId"] == product_b
    assert c_queue[0]["items"][0]["productId"] == product_c
    assert order["total"] == sum(
        s["subtotal"] - s["discount"] + s["shippingFee"] for s in order["shopOrders"]
    )


async def test_e2e_03_abandoned_payment_returns_the_stock(base_url, monkeypatch):
    _, product = await open_shop(base_url, USER_B_ID, "Shop B", 100_000, 4)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={"address": ADDRESS, "items": [{"productId": product, "qty": 2}]},
            )
        ).json()
        held = (await client.get(f"{base_url}/products/{product}")).json()

        # The buyer walks away; the hold lapses.
        monkeypatch.setattr(settings, "order_hold_minutes", 0)
        listed = (
            await client.get(f"{base_url}/orders", headers=auth(buyer))
        ).json()["items"][0]
        back = (await client.get(f"{base_url}/products/{product}")).json()

        # And paying it now is refused — there is nothing left to pay for.
        late = await pay(client, base_url, order)

    assert held["stock"] == 2
    assert listed["status"] == "CANCELLED"
    assert back["stock"] == 4
    assert late.status_code == 409
