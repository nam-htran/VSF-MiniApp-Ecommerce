"""Product options — size, colour — and the stock that hangs off them.

Options are optional: a product without them behaves exactly as before,
which the rest of the suite already covers. What is new, and what these
tests hold down:

  buying one size does not drain another
  a product with options refuses a line that doesn't name one
  two buyers racing for the last unit of one size: exactly one wins
  the option's own price is what gets charged
  the label is snapshotted onto the receipt
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


ADDRESS = "12 Lê Lợi, Q1, HCM"


async def shirt_with_sizes(base_url: str, seller: str, variants: list[dict]) -> dict:
    """A shop with one product that has size options."""
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
                "name": "Áo thun",
                "description": ".",
                "price": 100_000,
                # Ignored once options exist — the options carry the stock.
                "stock": 0,
                "category": "thoi-trang",
                "variants": variants,
            },
        )
    return created.json()


async def test_buying_one_size_does_not_drain_another(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shirt_with_sizes(
        base_url,
        seller,
        [
            {"options": {"Size": "M"}, "stock": 3},
            {"options": {"Size": "L"}, "stock": 7},
        ],
    )
    medium = next(v for v in product["variants"] if v["label"] == "M")
    large = next(v for v in product["variants"] if v["label"] == "L")

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={
                "address": ADDRESS,
                "items": [
                    {"productId": product["id"], "variantId": medium["id"], "qty": 2}
                ],
            },
        )
        after = (await client.get(f"{base_url}/products/{product['id']}")).json()

    sizes = {v["label"]: v["stock"] for v in after["variants"]}
    assert sizes["M"] == 1  # 3 - 2
    assert sizes["L"] == 7  # untouched
    # The product's own figure is the total of its options, not a third
    # number kept in parallel.
    assert after["stock"] == 8
    assert large["stock"] == 7


async def test_a_product_with_options_refuses_a_line_without_one(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shirt_with_sizes(
        base_url, seller, [{"options": {"Size": "M"}, "stock": 5}]
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={
                "address": ADDRESS,
                "items": [{"productId": product["id"], "qty": 1}],
            },
        )
        after = (await client.get(f"{base_url}/products/{product['id']}")).json()

    assert response.status_code == 409
    assert "phân loại" in response.json()["detail"]
    # Nothing half-happened.
    assert after["variants"][0]["stock"] == 5


async def test_two_buyers_race_for_the_last_of_one_size(base_url):
    """INV-05 again, one level down: the lock is on the option's row."""
    seller = await token_for(base_url, USER_B_ID)
    product = await shirt_with_sizes(
        base_url, seller, [{"options": {"Size": "M"}, "stock": 1}]
    )
    variant = product["variants"][0]["id"]
    buyer_1 = await token_for(base_url, USER_A_ID)
    buyer_2 = await token_for(base_url, USER_C_ID)

    async with httpx.AsyncClient() as client:
        payload = {
            "address": ADDRESS,
            "items": [
                {"productId": product["id"], "variantId": variant, "qty": 1}
            ],
        }
        first, second = await asyncio.gather(
            client.post(f"{base_url}/orders", headers=auth(buyer_1), json=payload),
            client.post(f"{base_url}/orders", headers=auth(buyer_2), json=payload),
        )
        after = (await client.get(f"{base_url}/products/{product['id']}")).json()

    assert sorted([first.status_code, second.status_code]) == [201, 409]
    assert after["variants"][0]["stock"] == 0


async def test_the_options_own_price_is_charged_and_its_label_kept(base_url):
    seller = await token_for(base_url, USER_B_ID)
    buyer = await token_for(base_url, USER_A_ID)
    product = await shirt_with_sizes(
        base_url,
        seller,
        [
            {"options": {"Size": "M"}, "stock": 5},
            # A 2XL costs more than the product's 100.000₫.
            {"options": {"Size": "2XL"}, "stock": 5, "price": 130_000},
        ],
    )
    big = next(v for v in product["variants"] if v["label"] == "2XL")

    async with httpx.AsyncClient() as client:
        order = (
            await client.post(
                f"{base_url}/orders",
                headers=auth(buyer),
                json={
                    "address": ADDRESS,
                    "items": [
                        {"productId": product["id"], "variantId": big["id"], "qty": 2}
                    ],
                },
            )
        ).json()

    item = order["shopOrders"][0]["items"][0]
    assert item["price"] == 130_000
    assert item["variantLabel"] == "2XL"
    assert order["shopOrders"][0]["subtotal"] == 260_000


async def test_editing_options_keeps_ids_and_drops_removed_ones(base_url):
    """A seller changing quantities must not reset the stock of the rest,
    nor orphan the row an existing order points at."""
    seller = await token_for(base_url, USER_B_ID)
    product = await shirt_with_sizes(
        base_url,
        seller,
        [
            {"options": {"Size": "M"}, "stock": 5},
            {"options": {"Size": "L"}, "stock": 6},
        ],
    )
    before = {v["label"]: v["id"] for v in product["variants"]}

    async with httpx.AsyncClient() as client:
        updated = (
            await client.patch(
                f"{base_url}/products/{product['id']}",
                headers=auth(seller),
                json={
                    "variants": [
                        {"options": {"Size": "M"}, "stock": 9},
                        {"options": {"Size": "XL"}, "stock": 4},
                    ]
                },
            )
        ).json()

    after = {v["label"]: v for v in updated["variants"]}
    # M kept its identity and took the new quantity.
    assert after["M"]["id"] == before["M"]
    assert after["M"]["stock"] == 9
    # L was removed, XL added.
    assert "L" not in after
    assert after["XL"]["stock"] == 4
