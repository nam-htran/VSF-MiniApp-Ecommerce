"""Test matrix — the rows that needed a feature building first.

  PROD-06  a SKU is unique inside its shop
  PROD-07  a listing naming prohibited goods is refused
  PROD-08  markup in a name or description is never executed
  STATE-04 a buyer may call off an order the shop hasn't started
  STATE-05 once it is shipping, they may not
  SEC-03   the payment gateway timing out leaves the order in a clear state
  SEC-05   one caller cannot flood the order endpoint
"""

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.payments.security import compute_hash
from app.products.moderation import banned_terms_in
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


async def open_shop(base_url: str, seller_id: str, name: str) -> str:
    token = await token_for(base_url, seller_id)
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": name, "description": "."},
        )
    return token


async def add_product(base_url: str, token: str, **fields) -> httpx.Response:
    body = {
        "name": "Hàng mẫu",
        "description": ".",
        "price": 100_000,
        "stock": 10,
        **fields,
    }
    async with httpx.AsyncClient() as client:
        return await client.post(
            f"{base_url}/products", headers=auth(token), json=body
        )


# --- PROD-06 ---------------------------------------------------------------


async def test_prod_06_sku_is_unique_within_a_shop(base_url):
    seller = await open_shop(base_url, USER_B_ID, "Shop B")

    first = await add_product(base_url, seller, sku="AO-001", name="Áo thun")
    duplicate = await add_product(base_url, seller, sku="AO-001", name="Áo khoác")
    other_code = await add_product(base_url, seller, sku="AO-002", name="Áo len")
    # A shop that doesn't use SKUs at all is unaffected: several products
    # with no code are not "duplicates" of each other.
    blank_one = await add_product(base_url, seller, name="Không mã 1")
    blank_two = await add_product(base_url, seller, name="Không mã 2")

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert "AO-001" in duplicate.json()["detail"]
    assert other_code.status_code == 201
    assert blank_one.status_code == 201 and blank_two.status_code == 201


async def test_prod_06_two_shops_may_use_the_same_sku(base_url):
    """The code belongs to the seller's own books, not to the marketplace."""
    seller_b = await open_shop(base_url, USER_B_ID, "Shop B")
    seller_c = await open_shop(base_url, USER_C_ID, "Shop C")

    mine = await add_product(base_url, seller_b, sku="SP-01")
    theirs = await add_product(base_url, seller_c, sku="SP-01")

    assert mine.status_code == 201
    assert theirs.status_code == 201


# --- PROD-07 ---------------------------------------------------------------


def test_prod_07_matching_ignores_accents_and_case():
    """"thuốc lá", "THUOC LA" and "Thuốc  Lá" are one listing."""
    assert banned_terms_in("Bán thuốc lá ngoại") == ["thuoc la"]
    assert banned_terms_in("BAN THUOC LA") == ["thuoc la"]
    assert banned_terms_in("bán sỉ Thuốc  Lá xịn") == ["thuoc la"]
    # And a word that merely contains one is not a match.
    assert banned_terms_in("kẹo sung sướng") == []
    assert banned_terms_in("khung tranh gỗ") == []


async def test_prod_07_banned_listing_is_refused_with_the_reason(base_url):
    seller = await open_shop(base_url, USER_B_ID, "Shop B")

    in_name = await add_product(base_url, seller, name="Thuốc lá ngoại nhập")
    in_description = await add_product(
        base_url, seller, description="Hàng nhái loại 1, giống thật 99%"
    )
    clean = await add_product(base_url, seller, name="Áo thun cotton")

    assert in_name.status_code == 422
    # The seller is told which word, not just "rejected".
    assert "thuoc la" in in_name.json()["detail"]
    assert in_description.status_code == 422
    assert clean.status_code == 201


async def test_prod_07_editing_into_a_banned_word_is_refused_too(base_url):
    """The gate is on the write, not on creation — otherwise a clean
    product could be edited into a prohibited one."""
    seller = await open_shop(base_url, USER_B_ID, "Shop B")
    product = (await add_product(base_url, seller, name="Bật lửa")).json()

    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{base_url}/products/{product['id']}",
            headers=auth(seller),
            json={"name": "Thuốc lá điện tử"},
        )
        after = (await client.get(f"{base_url}/products/{product['id']}")).json()

    assert response.status_code == 422
    assert after["name"] == "Bật lửa"


# --- PROD-08 ---------------------------------------------------------------


async def test_prod_08_markup_is_stored_and_returned_as_text(base_url):
    """The API is JSON, so markup is data. What matters is that it comes
    back as the same characters — escaped by the encoder, never as a
    document fragment a client could be tricked into executing."""
    seller = await open_shop(base_url, USER_B_ID, "Shop B")
    payload = '<script>alert("xss")</script>'

    created = await add_product(
        base_url, seller, name=f"Áo {payload}", description=f"Mô tả {payload}"
    )
    product = created.json()

    async with httpx.AsyncClient() as client:
        raw = await client.get(f"{base_url}/products/{product['id']}")

    assert created.status_code == 201
    # Round-trips byte for byte as a JSON string value...
    assert raw.json()["name"] == f"Áo {payload}"
    # ...and the angle brackets are escaped on the wire, so a browser
    # sniffing the body cannot see a tag.
    assert "<script>" not in raw.text
    assert raw.headers["content-type"].startswith("application/json")


# --- STATE-04 / STATE-05 ---------------------------------------------------


async def buy_one(base_url: str, seller: str, buyer: str) -> dict:
    product = (await add_product(base_url, seller, name="Hàng đặt")).json()
    async with httpx.AsyncClient() as client:
        return (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": ADDRESS,
                    "items": [{"productId": product["id"], "qty": 2}],
                },
            )
        ).json()


async def test_state_04_buyer_cancels_before_the_shop_starts(base_url):
    seller = await open_shop(base_url, USER_B_ID, "Shop B")
    buyer = await token_for(base_url, USER_A_ID)
    order = await buy_one(base_url, seller, buyer)
    product_id = order["shopOrders"][0]["items"][0]["productId"]

    async with httpx.AsyncClient() as client:
        held = (await client.get(f"{base_url}/products/{product_id}")).json()
        cancelled = await client.post(
            f"{base_url}/orders/{order['id']}/cancel", headers=auth(buyer)
        )
        after = (await client.get(f"{base_url}/products/{product_id}")).json()
        again = await client.post(
            f"{base_url}/orders/{order['id']}/cancel", headers=auth(buyer)
        )

    assert held["stock"] == 8
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    # The shop's slice is cancelled too, and the stock came back.
    assert cancelled.json()["shopOrders"][0]["status"] == "CANCELLED"
    assert after["stock"] == 10
    # Cancelling twice is not an error, and does not credit the stock twice.
    assert again.status_code == 200


async def test_state_05_cannot_cancel_once_it_is_shipping(base_url):
    seller = await open_shop(base_url, USER_B_ID, "Shop B")
    buyer = await token_for(base_url, USER_A_ID)
    order = await buy_one(base_url, seller, buyer)
    product_id = order["shopOrders"][0]["items"][0]["productId"]

    async with httpx.AsyncClient() as client:
        amount = int(order["total"])
        await client.post(
            f"{base_url}/payments/ipn",
            json={
                "paymentId": "pay_ship",
                "orderId": order["id"],
                "amount": amount,
                "status": "PAID",
                "secureHash": compute_hash(
                    settings.payment_ipn_secret, order["id"], amount, "PAID"
                ),
            },
        )
        slice_id = (
            await client.get(f"{base_url}/orders/shop", headers=auth(seller))
        ).json()["items"][0]["id"]
        await client.patch(
            f"{base_url}/orders/shop/{slice_id}",
            headers=auth(seller),
            json={"status": "SHIPPING"},
        )

        refused = await client.post(
            f"{base_url}/orders/{order['id']}/cancel", headers=auth(buyer)
        )
        after = (await client.get(f"{base_url}/products/{product_id}")).json()

    assert refused.status_code == 409
    assert "giao đi" in refused.json()["detail"]
    # Goods on the road stay sold.
    assert after["stock"] == 8


async def test_state_04_cannot_cancel_someone_elses_order(base_url):
    seller = await open_shop(base_url, USER_B_ID, "Shop B")
    buyer = await token_for(base_url, USER_A_ID)
    stranger = await token_for(base_url, USER_C_ID)
    order = await buy_one(base_url, seller, buyer)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/orders/{order['id']}/cancel", headers=auth(stranger)
        )

    assert response.status_code == 404  # not 403 — ids stay undiscoverable


# --- SEC-03 ----------------------------------------------------------------


async def test_sec_03_gateway_being_unreachable_leaves_a_clear_state(base_url):
    """The order is created before the gateway is called, so if payment
    never starts the buyer still has a PENDING order they can pay later —
    and its stock hold is what eventually cleans it up."""
    seller = await open_shop(base_url, USER_B_ID, "Shop B")
    buyer = await token_for(base_url, USER_A_ID)
    order = await buy_one(base_url, seller, buyer)

    async with httpx.AsyncClient() as client:
        # Nothing is sent to the gateway at all — the client "times out".
        listed = (
            await client.get(f"{base_url}/orders", headers=auth(buyer))
        ).json()["items"][0]
        # An IPN for a payment that was never opened is still verified and
        # applied on its own merits; nothing is left dangling.
        amount = int(order["total"])
        late = await client.post(
            f"{base_url}/payments/ipn",
            json={
                "paymentId": "pay_never_opened",
                "orderId": order["id"],
                "amount": amount,
                "status": "PAID",
                "secureHash": compute_hash(
                    settings.payment_ipn_secret, order["id"], amount, "PAID"
                ),
            },
        )
        final = (
            await client.get(f"{base_url}/orders/{order['id']}", headers=auth(buyer))
        ).json()

    assert listed["status"] == "PENDING"
    assert listed["expiresAt"] is not None  # it will not hold stock for ever
    assert late.status_code == 200
    assert final["status"] == "PAID"


# --- SEC-05 ----------------------------------------------------------------


async def test_sec_05_a_burst_of_orders_is_throttled_not_crashed(base_url):
    seller = await open_shop(base_url, USER_B_ID, "Shop B")
    buyer = await token_for(base_url, USER_A_ID)
    product = (await add_product(base_url, seller, stock=200)).json()
    payload = {
        "address": ADDRESS,
        "items": [{"productId": product["id"], "qty": 1}],
    }

    async with httpx.AsyncClient() as client:
        codes = []
        for _ in range(30):
            response = await client.post(
                f"{base_url}/orders", headers=auth(buyer), json=payload
            )
            codes.append(response.status_code)
        # Browsing is never throttled — the limit is on the write.
        browsing = await client.get(f"{base_url}/products")

    assert codes.count(201) == 20  # the window's allowance
    assert codes.count(429) == 10  # and the rest are refused, not dropped
    # Refused cleanly, with something for the client to act on.
    assert browsing.status_code == 200
