"""Sale vouchers.

The rule that matters: the price a card advertises is the price the order
charges. Both go through `discount_for`, and these tests hold the two ends
together.

  the best live voucher applies itself — nobody types a code
  an expired or not-yet-started voucher discounts nothing and lists nowhere
  a percentage voucher is capped by max_discount
  min_order gates the voucher
  a discount never exceeds the subtotal
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.vouchers.store import Voucher, discount_for
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


def window(start_days: int, end_days: int) -> dict:
    """A voucher window relative to now, in days."""
    now = datetime.now(timezone.utc)
    return {
        "startsAt": (now + timedelta(days=start_days)).isoformat(),
        "endsAt": (now + timedelta(days=end_days)).isoformat(),
    }


async def shop_with_product(base_url: str, seller: str, price: int) -> str:
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(seller),
            json={"name": "Shop B", "description": "."},
        )
        created = await client.post(
            f"{base_url}/products",
            headers=auth(seller),
            json={"name": "Bàn phím", "description": ".", "price": price, "stock": 10},
        )
    return created.json()["id"]


# --- the arithmetic, unit-level: one implementation, so pin it down ---


def voucher(**kwargs) -> Voucher:
    base = dict(
        id="v",
        code="C",
        description="d",
        shop_id=None,
        discount_type="AMOUNT",
        discount_value=Decimal("10000"),
        max_discount=None,
        min_order=Decimal("0"),
        status="ACTIVE",
    )
    base.update(kwargs)
    return Voucher(**base)


def test_amount_voucher_takes_its_face_value():
    assert discount_for(voucher(), Decimal("50000")) == Decimal("10000.00")


def test_percent_voucher_is_capped():
    capped = voucher(
        discount_type="PERCENT",
        discount_value=Decimal("50"),
        max_discount=Decimal("30000"),
    )
    # 50% of 200k is 100k, but the cap says 30k.
    assert discount_for(capped, Decimal("200000")) == Decimal("30000.00")
    # Under the cap it is just the percentage.
    assert discount_for(capped, Decimal("40000")) == Decimal("20000.00")


def test_min_order_gates_the_voucher():
    gated = voucher(min_order=Decimal("100000"))
    assert discount_for(gated, Decimal("99999")) == Decimal("0")
    assert discount_for(gated, Decimal("100000")) == Decimal("10000.00")


def test_discount_never_exceeds_the_subtotal():
    big = voucher(discount_value=Decimal("500000"))
    # A 500k voucher on a 60k basket takes 60k — never more, never negative.
    assert discount_for(big, Decimal("60000")) == Decimal("60000.00")


# --- end to end: advertised price == charged price ---


async def test_best_live_voucher_prices_the_card_and_the_order(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shop_with_product(base_url, seller, 200_000)

    async with httpx.AsyncClient() as client:
        # Two live vouchers; the better one must win.
        await client.post(
            f"{base_url}/vouchers",
            headers=auth(seller),
            json={
                "code": "SMALL10",
                "description": "Giảm 10.000₫",
                "discountType": "AMOUNT",
                "discountValue": 10_000,
                **window(-1, 7),
            },
        )
        await client.post(
            f"{base_url}/vouchers",
            headers=auth(seller),
            json={
                "code": "BIG25",
                "description": "Giảm 25% tối đa 60.000₫",
                "discountType": "PERCENT",
                "discountValue": 25,
                "maxDiscount": 60_000,
                **window(-1, 7),
            },
        )

        detail = (await client.get(f"{base_url}/products/{product}")).json()
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": "12 Lê Lợi, Q1, HCM",
                    "items": [{"productId": product, "qty": 1}],
                },
            )
        ).json()

    # 25% of 200k = 50k, under the 60k cap, and beats the flat 10k.
    assert detail["voucher"]["code"] == "BIG25"
    assert detail["effectivePrice"] == 150_000

    shop_order = order["shopOrders"][0]
    assert shop_order["voucherCode"] == "BIG25"
    assert shop_order["discount"] == 50_000
    # The card promised 150k; the order charges 150k + shipping.
    assert order["total"] == detail["effectivePrice"] + shop_order["shippingFee"]


async def test_expired_voucher_discounts_nothing_and_lists_nowhere(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shop_with_product(base_url, seller, 200_000)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/vouchers",
            headers=auth(seller),
            json={
                "code": "GONE",
                "description": "Đã hết hạn",
                "discountType": "AMOUNT",
                "discountValue": 50_000,
                **window(-10, -1),  # ended yesterday
            },
        )
        await client.post(
            f"{base_url}/vouchers",
            headers=auth(seller),
            json={
                "code": "SOON",
                "description": "Chưa bắt đầu",
                "discountType": "AMOUNT",
                "discountValue": 70_000,
                **window(3, 10),  # starts in three days
            },
        )

        live = (await client.get(f"{base_url}/vouchers")).json()
        detail = (await client.get(f"{base_url}/products/{product}")).json()
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": "12 Lê Lợi, Q1, HCM",
                    "items": [{"productId": product, "qty": 1}],
                },
            )
        ).json()

    # Neither shows in the promo strip...
    assert live["items"] == []
    # ...nor touches the price, on the card or on the bill.
    assert detail["voucher"] is None
    assert detail["effectivePrice"] == 200_000
    assert order["shopOrders"][0]["discount"] == 0
    assert order["shopOrders"][0]["voucherCode"] is None


async def test_min_order_voucher_waits_for_a_big_enough_basket(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shop_with_product(base_url, seller, 100_000)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/vouchers",
            headers=auth(seller),
            json={
                "code": "OVER150",
                "description": "Giảm 40.000₫ cho đơn từ 150.000₫",
                "discountType": "AMOUNT",
                "discountValue": 40_000,
                "minOrder": 150_000,
                **window(-1, 7),
            },
        )

        # One unit is 100k — under the threshold, so the card shows full price.
        detail = (await client.get(f"{base_url}/products/{product}")).json()
        # Two units are 200k, so the order does get the discount.
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": "12 Lê Lợi, Q1, HCM",
                    "items": [{"productId": product, "qty": 2}],
                },
            )
        ).json()

    assert detail["voucher"] is None
    assert detail["effectivePrice"] == 100_000
    assert order["shopOrders"][0]["discount"] == 40_000


async def test_category_voucher_only_counts_its_own_category(base_url):
    """A "giảm cho thời trang" voucher must not be earned by a keyboard."""
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(seller),
            json={"name": "Shop B", "description": "."},
        )
        shirt = (
            await client.post(
                f"{base_url}/products",
                headers=auth(seller),
                json={
                    "name": "Áo",
                    "description": ".",
                    "price": 100_000,
                    "stock": 10,
                    "category": "thoi-trang",
                },
            )
        ).json()["id"]
        keyboard = (
            await client.post(
                f"{base_url}/products",
                headers=auth(seller),
                json={
                    "name": "Bàn phím",
                    "description": ".",
                    "price": 500_000,
                    "stock": 10,
                    "category": "dien-tu",
                },
            )
        ).json()["id"]

        await client.post(
            f"{base_url}/vouchers",
            headers=auth(seller),
            json={
                "code": "THOITRANG20",
                "description": "Giảm 20% thời trang",
                "category": "thoi-trang",
                "discountType": "PERCENT",
                "discountValue": 20,
                **window(-1, 7),
            },
        )

        # The keyboard alone earns nothing, however expensive.
        only_keyboard = (
            await client.post(
                f"{base_url}/orders/quote",
                json={"items": [{"productId": keyboard, "qty": 1}]},
            )
        ).json()
        # Both together: 20% of the shirt only, not of the 600k basket.
        both = (
            await client.post(
                f"{base_url}/orders/quote",
                json={
                    "items": [
                        {"productId": keyboard, "qty": 1},
                        {"productId": shirt, "qty": 1},
                    ]
                },
            )
        ).json()
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": "12 Lê Lợi, Q1, HCM",
                    "items": [
                        {"productId": keyboard, "qty": 1},
                        {"productId": shirt, "qty": 1},
                    ],
                },
            )
        ).json()

    assert only_keyboard["discount"] == 0
    assert both["discount"] == 20_000  # 20% of 100k, not of 600k
    assert order["shopOrders"][0]["discount"] == 20_000


async def test_quote_lists_unusable_vouchers_with_a_reason(base_url):
    seller = await token_for(base_url, USER_B_ID)
    product = await shop_with_product(base_url, seller, 100_000)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/vouchers",
            headers=auth(seller),
            json={
                "code": "NEED500",
                "description": "Giảm 60.000₫ cho đơn từ 500.000₫",
                "discountType": "AMOUNT",
                "discountValue": 60_000,
                "minOrder": 500_000,
                **window(-1, 7),
            },
        )
        quoted = (
            await client.post(
                f"{base_url}/orders/quote",
                json={"items": [{"productId": product, "qty": 1}]},
            )
        ).json()

    offer = quoted["shops"][0]["vouchers"][0]
    # Shown, but greyed out and explained — not hidden.
    assert offer["code"] == "NEED500"
    assert offer["applicable"] is False
    assert "400000" in offer["reason"].replace(".", "").replace(",", "")
    assert quoted["discount"] == 0


async def test_buyer_can_pick_a_voucher_and_a_bogus_pick_falls_back(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shop_with_product(base_url, seller, 200_000)

    async with httpx.AsyncClient() as client:
        shop_id = (
            await client.get(f"{base_url}/products/{product}")
        ).json()["shopId"]
        for code, value in (("SMALL", 10_000), ("LARGE", 80_000)):
            await client.post(
                f"{base_url}/vouchers",
                headers=auth(seller),
                json={
                    "code": code,
                    "description": code,
                    "discountType": "AMOUNT",
                    "discountValue": value,
                    **window(-1, 7),
                },
            )

        items = [{"productId": product, "qty": 1}]
        # Deliberately choosing the worse one is allowed — it is the buyer's
        # basket.
        picked = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": "12 Lê Lợi, Q1, HCM",
                    "items": items,
                    "voucherCodes": {shop_id: "SMALL"},
                },
            )
        ).json()
        # A code that isn't theirs falls back to the best, never to an error.
        bogus = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": "12 Lê Lợi, Q1, HCM",
                    "items": items,
                    "voucherCodes": {shop_id: "NOT-A-CODE"},
                },
            )
        ).json()

    assert picked["shopOrders"][0]["voucherCode"] == "SMALL"
    assert picked["shopOrders"][0]["discount"] == 10_000
    assert bogus["shopOrders"][0]["voucherCode"] == "LARGE"
    assert bogus["shopOrders"][0]["discount"] == 80_000


async def test_a_seller_cannot_reuse_a_code(base_url):
    seller = await token_for(base_url, USER_B_ID)
    await shop_with_product(base_url, seller, 100_000)
    body = {
        "code": "DUP",
        "description": "x",
        "discountType": "AMOUNT",
        "discountValue": 1000,
        **window(-1, 7),
    }
    async with httpx.AsyncClient() as client:
        first = await client.post(
            f"{base_url}/vouchers", headers=auth(seller), json=body
        )
        second = await client.post(
            f"{base_url}/vouchers", headers=auth(seller), json=body
        )
    assert first.status_code == 201
    assert second.status_code == 409


async def test_buyers_cannot_create_vouchers(base_url):
    buyer = await token_for(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/vouchers",
            headers=auth(buyer),
            json={
                "code": "NOPE",
                "description": "x",
                "discountType": "AMOUNT",
                "discountValue": 1000,
                **window(-1, 7),
            },
        )
    assert response.status_code == 403
