"""Orders, model B.

The rules under test:
  ORD-01  a cart spanning two shops becomes one order with two shop orders
  ORD-02  prices are snapshotted — a later price change leaves receipts alone
  INV-05  two buyers racing for the last unit: exactly one wins
  stock and money never come from the client
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


async def shop_with_product(
    base_url: str, vapp_user_id: str, shop_name: str, product: dict
) -> str:
    """Open a shop, add one product, return the product id."""
    token = await token_for(base_url, vapp_user_id)
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": shop_name, "description": "..."},
        )
        created = await client.post(
            f"{base_url}/products", headers=auth(token), json=product
        )
    return created.json()["id"]


ADDRESS = "Số 7 Bằng Lăng 1, Vinhomes Riverside, Hà Nội"


async def test_cart_spanning_two_shops_splits_into_shop_orders(base_url):
    keyboard = await shop_with_product(
        base_url,
        USER_B_ID,
        "Shop B",
        {"name": "Bàn phím", "description": ".", "price": 690000, "stock": 10},
    )
    tshirt = await shop_with_product(
        base_url,
        USER_C_ID,
        "Shop C",
        {"name": "Áo thun", "description": ".", "price": 129000, "stock": 10},
    )
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={
                "address": ADDRESS,
                "items": [
                    {"productId": keyboard, "qty": 2},
                    {"productId": tshirt, "qty": 3},
                ],
            },
        )
        keyboard_after = await client.get(f"{base_url}/products/{keyboard}")

    assert response.status_code == 201
    order = response.json()

    # One payment, two deliveries.
    assert order["status"] == "PENDING"
    assert len(order["shopOrders"]) == 2
    by_shop = {so["shopName"]: so for so in order["shopOrders"]}
    assert by_shop["Shop B"]["subtotal"] == 2 * 690000
    assert by_shop["Shop C"]["subtotal"] == 3 * 129000

    # Total = subtotals + one shipping fee PER SHOP, itemised (rule 5.2.1).
    fees = sum(so["shippingFee"] for so in order["shopOrders"])
    assert fees == 2 * order["shopOrders"][0]["shippingFee"]
    assert order["total"] == 2 * 690000 + 3 * 129000 + fees

    # Stock came down inside the same transaction.
    assert keyboard_after.json()["stock"] == 8


async def test_receipts_keep_the_purchase_price(base_url):
    seller = await token_for(base_url, USER_B_ID)
    product = await shop_with_product(
        base_url,
        USER_B_ID,
        "Shop B",
        {"name": "Loa", "description": ".", "price": 1290000, "stock": 5},
    )
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        placed = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={"address": ADDRESS, "items": [{"productId": product, "qty": 1}]},
        )
        # The seller doubles the price afterwards.
        await client.patch(
            f"{base_url}/products/{product}",
            headers=auth(seller),
            json={"price": 2580000},
        )
        fetched = await client.get(
            f"{base_url}/orders/{placed.json()['id']}", headers=auth(buyer)
        )

    item = fetched.json()["shopOrders"][0]["items"][0]
    assert item["price"] == 1290000  # the photograph, not the window


async def test_out_of_stock_rejects_the_whole_order(base_url):
    product = await shop_with_product(
        base_url,
        USER_B_ID,
        "Shop B",
        {"name": "Máy ảnh", "description": ".", "price": 6490000, "stock": 3},
    )
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={"address": ADDRESS, "items": [{"productId": product, "qty": 4}]},
        )
        after = await client.get(f"{base_url}/products/{product}")
        mine = await client.get(f"{base_url}/orders", headers=auth(buyer))

    assert response.status_code == 409
    # Nothing half-happened: stock untouched, no order created.
    assert after.json()["stock"] == 3
    assert mine.json()["items"] == []


async def test_two_buyers_race_for_the_last_unit(base_url):
    """INV-05 — the reason this project runs on Postgres."""
    product = await shop_with_product(
        base_url,
        USER_B_ID,
        "Shop B",
        {"name": "Hàng hiếm", "description": ".", "price": 100000, "stock": 1},
    )
    buyer_1 = await token_for(base_url, USER_A_ID)
    buyer_2 = await token_for(base_url, USER_C_ID)

    async with httpx.AsyncClient() as client:
        payload = {
            "address": ADDRESS,
            "items": [{"productId": product, "qty": 1}],
        }
        first, second = await asyncio.gather(
            client.post(f"{base_url}/orders", headers=auth(buyer_1), json=payload),
            client.post(f"{base_url}/orders", headers=auth(buyer_2), json=payload),
        )
        after = await client.get(f"{base_url}/products/{product}")

    # Exactly one winner — never zero, never two.
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    assert after.json()["stock"] == 0


async def test_duplicate_lines_merge_instead_of_double_locking(base_url):
    product = await shop_with_product(
        base_url,
        USER_B_ID,
        "Shop B",
        {"name": "Bình nước", "description": ".", "price": 220000, "stock": 10},
    )
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={
                "address": ADDRESS,
                "items": [
                    {"productId": product, "qty": 1},
                    {"productId": product, "qty": 2},
                ],
            },
        )

    items = response.json()["shopOrders"][0]["items"]
    assert len(items) == 1
    assert items[0]["qty"] == 3


async def test_orders_are_private(base_url):
    product = await shop_with_product(
        base_url,
        USER_B_ID,
        "Shop B",
        {"name": "Đèn", "description": ".", "price": 350000, "stock": 5},
    )
    buyer = await token_for(base_url, USER_A_ID)
    other = await token_for(base_url, USER_C_ID)

    async with httpx.AsyncClient() as client:
        placed = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={"address": ADDRESS, "items": [{"productId": product, "qty": 1}]},
        )
        order_id = placed.json()["id"]

        theirs = await client.get(
            f"{base_url}/orders/{order_id}", headers=auth(other)
        )
        their_list = await client.get(f"{base_url}/orders", headers=auth(other))
        anonymous = await client.post(
            f"{base_url}/orders",
            json={"address": ADDRESS, "items": [{"productId": product, "qty": 1}]},
        )

    assert theirs.status_code == 404  # not 403 — ids stay undiscoverable
    assert their_list.json()["items"] == []
    assert anonymous.status_code == 401
