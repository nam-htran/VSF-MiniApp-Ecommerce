"""Stock held during checkout, and handed back when nobody pays.

Placing an order decrements stock immediately — that is what stops two
buyers claiming the last unit (INV-05). The cost is that an abandoned
checkout would hold that unit for ever, so the hold expires.

  an unpaid order past its window is cancelled and its stock returned
  a paid order keeps its stock: the hold became a sale
  a fresh unpaid order is left alone
  the unit really is buyable again afterwards
  sweeping twice does not hand the same stock back twice
  a variant's stock returns to that variant, not the product
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


async def shop_with_product(base_url: str, seller: str, stock: int, **extra) -> dict:
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(seller),
            json={"name": "Shop B", "description": "."},
        )
        created = await client.post(
            f"{base_url}/products",
            headers=auth(seller),
            json={
                "name": "Hàng hiếm",
                "description": ".",
                "price": 100_000,
                "stock": stock,
                **extra,
            },
        )
    return created.json()


async def expire_now(monkeypatch) -> None:
    """Shrink the hold to nothing so the next sweep treats orders as stale."""
    monkeypatch.setattr(settings, "order_hold_minutes", 0)


async def test_unpaid_order_gives_its_stock_back(base_url, monkeypatch):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shop_with_product(base_url, seller, 3)

    async with httpx.AsyncClient() as client:
        placed = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={
                "address": ADDRESS,
                "items": [{"productId": product["id"], "qty": 2}],
            },
        )
        held = (await client.get(f"{base_url}/products/{product['id']}")).json()

        # A PENDING order advertises when its hold runs out.
        assert placed.json()["expiresAt"] is not None

        await expire_now(monkeypatch)
        # Any call that sweeps will do; listing orders is the buyer's own.
        after_sweep = await client.get(f"{base_url}/orders", headers=auth(buyer))
        back = (await client.get(f"{base_url}/products/{product['id']}")).json()

    assert held["stock"] == 1  # 3 - 2 while held
    assert back["stock"] == 3  # returned in full
    order = after_sweep.json()["items"][0]
    assert order["status"] == "CANCELLED"
    assert order["expiresAt"] is None  # nothing is held any more


async def test_paid_order_keeps_its_stock(base_url, monkeypatch):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shop_with_product(base_url, seller, 3)

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": ADDRESS,
                    "items": [{"productId": product["id"], "qty": 2}],
                },
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

        await expire_now(monkeypatch)
        await client.get(f"{base_url}/orders", headers=auth(buyer))
        after = (await client.get(f"{base_url}/products/{product['id']}")).json()
        fetched = await client.get(
            f"{base_url}/orders/{order['id']}", headers=auth(buyer)
        )

    # The hold became a sale; nothing goes back.
    assert after["stock"] == 1
    assert fetched.json()["status"] == "PAID"
    assert fetched.json()["expiresAt"] is None


async def test_a_fresh_unpaid_order_is_left_alone(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shop_with_product(base_url, seller, 3)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={
                "address": ADDRESS,
                "items": [{"productId": product["id"], "qty": 2}],
            },
        )
        listed = await client.get(f"{base_url}/orders", headers=auth(buyer))
        after = (await client.get(f"{base_url}/products/{product['id']}")).json()

    assert listed.json()["items"][0]["status"] == "PENDING"
    assert after["stock"] == 1  # still held


async def test_released_stock_can_be_bought_by_someone_else(base_url, monkeypatch):
    """The whole point: the abandoned unit goes back on sale."""
    seller = await token_for(base_url, USER_B_ID)
    first = await token_for(base_url, USER_A_ID)
    second = await token_for(base_url, USER_C_ID)
    product = await shop_with_product(base_url, seller, 1)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/orders",
            headers=auth(first),
            json={
                "address": ADDRESS,
                "items": [{"productId": product["id"], "qty": 1}],
            },
        )
        # With the last unit held, the second buyer cannot have it.
        blocked = await client.post(
            f"{base_url}/orders",
            headers=auth(second),
            json={
                "address": ADDRESS,
                "items": [{"productId": product["id"], "qty": 1}],
            },
        )

        await expire_now(monkeypatch)
        # Placing an order sweeps first, so this same call now succeeds.
        allowed = await client.post(
            f"{base_url}/orders",
            headers=auth(second),
            json={
                "address": ADDRESS,
                "items": [{"productId": product["id"], "qty": 1}],
            },
        )

    assert blocked.status_code == 409
    assert allowed.status_code == 201


async def test_sweeping_twice_does_not_return_the_stock_twice(base_url, monkeypatch):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shop_with_product(base_url, seller, 5)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={
                "address": ADDRESS,
                "items": [{"productId": product["id"], "qty": 3}],
            },
        )
        await expire_now(monkeypatch)
        for _ in range(3):
            await client.get(f"{base_url}/orders", headers=auth(buyer))
        after = (await client.get(f"{base_url}/products/{product['id']}")).json()

    # Back to 5, not 8 or 11 — the CANCELLED status is the guard.
    assert after["stock"] == 5


async def test_a_variants_stock_returns_to_that_variant(base_url, monkeypatch):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shop_with_product(
        base_url,
        seller,
        0,
        variants=[
            {"options": {"Size": "M"}, "stock": 4},
            {"options": {"Size": "L"}, "stock": 6},
        ],
    )
    medium = next(v for v in product["variants"] if v["label"] == "M")

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={
                "address": ADDRESS,
                "items": [
                    {"productId": product["id"], "variantId": medium["id"], "qty": 3}
                ],
            },
        )
        await expire_now(monkeypatch)
        await client.get(f"{base_url}/orders", headers=auth(buyer))
        after = (await client.get(f"{base_url}/products/{product['id']}")).json()

    sizes = {v["label"]: v["stock"] for v in after["variants"]}
    assert sizes["M"] == 4  # returned to M
    assert sizes["L"] == 6  # never touched
