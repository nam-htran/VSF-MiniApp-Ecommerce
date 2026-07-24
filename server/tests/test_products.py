"""Products.

The rules under test:
  a seller may only put products in their own shop
  a seller may only edit products in their own shop
  hidden products never reach the storefront
  the shop is taken from the caller, never from the request body
"""

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


async def seller_with_shop(base_url: str, vapp_user_id: str, shop_name: str):
    """Log in and open a shop. Opening the shop is what grants SELLER."""
    token = await token_for(base_url, vapp_user_id)
    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": shop_name, "description": "..."},
        )
    return token, created.json()["id"]


PRODUCT = {"name": "Ấm siêu tốc", "description": "1.8 lít", "price": 350000, "stock": 5}


async def test_seller_adds_a_product_to_their_own_shop(base_url):
    token, shop_id = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )

    assert response.status_code == 201
    body = response.json()
    # The shop is derived from the caller — the request never named one.
    assert body["shopId"] == shop_id
    assert body["price"] == 350000
    assert body["status"] == "ACTIVE"


async def test_buyer_cannot_add_a_product(base_url):
    token = await token_for(base_url, USER_B_ID)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )

    assert response.status_code == 403


async def test_seller_cannot_edit_another_shops_product(base_url):
    token_b, _ = await seller_with_shop(base_url, USER_B_ID, "Shop B")
    token_c, _ = await seller_with_shop(base_url, USER_C_ID, "Shop C")

    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/products", headers=auth(token_b), json=PRODUCT
        )
        product_id = created.json()["id"]

        response = await client.patch(
            f"{base_url}/products/{product_id}",
            headers=auth(token_c),
            json={"price": 1},
        )
        after = await client.get(f"{base_url}/products/{product_id}")

    assert response.status_code == 404
    assert after.json()["price"] == 350000


async def test_hidden_products_stay_out_of_the_storefront(base_url):
    token, shop_id = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )
        product_id = created.json()["id"]

        await client.patch(
            f"{base_url}/products/{product_id}",
            headers=auth(token),
            json={"status": "HIDDEN"},
        )

        storefront = await client.get(f"{base_url}/shops/{shop_id}/products")
        detail = await client.get(f"{base_url}/products/{product_id}")
        mine = await client.get(
            f"{base_url}/products/mine", headers=auth(token)
        )

    assert storefront.json()["items"] == []
    assert detail.status_code == 404
    # The seller still sees it, otherwise they could never unhide it.
    assert [p["id"] for p in mine.json()["items"]] == [product_id]


ADDRESS = "12 Đường Test, Q1, TPHCM"


async def test_deleting_a_never_ordered_product_removes_it(base_url):
    """No order ever pointed at it, so it is truly gone — row and variants."""
    token, shop_id = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )
        product_id = created.json()["id"]

        deleted = await client.delete(
            f"{base_url}/products/{product_id}", headers=auth(token)
        )
        detail = await client.get(f"{base_url}/products/{product_id}")
        mine = await client.get(
            f"{base_url}/products/mine", headers=auth(token)
        )

    assert deleted.status_code == 200
    assert deleted.json()["outcome"] == "deleted"
    assert detail.status_code == 404
    # Gone even from the seller's own list — a real delete, not a hide.
    assert mine.json()["items"] == []


async def test_deleting_an_ordered_product_archives_it(base_url):
    """An order line snapshots this product, so the row must survive; it just
    leaves every list and can no longer be bought."""
    token, _ = await seller_with_shop(base_url, USER_A_ID, "Shop A")
    buyer = await token_for(base_url, USER_B_ID)

    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )
        product_id = created.json()["id"]

        placed = await client.post(
            f"{base_url}/orders",
            headers=auth(buyer),
            json={"address": ADDRESS, "items": [{"productId": product_id, "qty": 1}]},
        )
        assert placed.status_code == 201

        deleted = await client.delete(
            f"{base_url}/products/{product_id}", headers=auth(token)
        )
        detail = await client.get(f"{base_url}/products/{product_id}")
        mine = await client.get(
            f"{base_url}/products/mine", headers=auth(token)
        )
        # The buyer's order still shows the product it snapshotted.
        orders = await client.get(f"{base_url}/orders", headers=auth(buyer))

    assert deleted.status_code == 200
    assert deleted.json()["outcome"] == "archived"
    # Off the storefront and out of the seller's own list...
    assert detail.status_code == 404
    assert mine.json()["items"] == []
    # ...but the order history is intact.
    ordered_ids = [
        item["productId"]
        for order in orders.json()["items"]
        for shop_order in order["shopOrders"]
        for item in shop_order["items"]
    ]
    assert product_id in ordered_ids


async def test_only_the_owner_can_delete_a_product(base_url):
    token_b, _ = await seller_with_shop(base_url, USER_B_ID, "Shop B")
    token_c, _ = await seller_with_shop(base_url, USER_C_ID, "Shop C")

    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{base_url}/products", headers=auth(token_b), json=PRODUCT
        )
        product_id = created.json()["id"]

        # Another seller gets 404, not 403 — same as edit, so the endpoint
        # can't confirm which ids exist.
        response = await client.delete(
            f"{base_url}/products/{product_id}", headers=auth(token_c)
        )
        still_there = await client.get(f"{base_url}/products/{product_id}")

    assert response.status_code == 404
    assert still_there.status_code == 200


async def test_negative_stock_is_rejected(base_url):
    token, _ = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/products",
            headers=auth(token),
            json={**PRODUCT, "stock": -1},
        )

    assert response.status_code == 422


async def test_marketplace_lists_products_across_shops(base_url):
    """The home screen shows one feed over every shop, no token needed."""
    token_b, _ = await seller_with_shop(base_url, USER_B_ID, "Shop B")
    token_c, _ = await seller_with_shop(base_url, USER_C_ID, "Shop C")

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/products", headers=auth(token_b), json=PRODUCT
        )
        await client.post(
            f"{base_url}/products",
            headers=auth(token_c),
            json={**PRODUCT, "name": "Bàn ủi hơi nước"},
        )

        response = await client.get(f"{base_url}/products")

    assert response.status_code == 200
    body = response.json()
    # Both shops present, each item naming its shop.
    assert {item["shopName"] for item in body["items"]} == {"Shop B", "Shop C"}
    assert body["hasMore"] is False


async def test_marketplace_feed_pages_and_hides_hidden(base_url):
    token, _ = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        first = await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )
        await client.post(
            f"{base_url}/products",
            headers=auth(token),
            json={**PRODUCT, "name": "Bình đun nước"},
        )
        await client.patch(
            f"{base_url}/products/{first.json()['id']}",
            headers=auth(token),
            json={"status": "HIDDEN"},
        )

        page = await client.get(f"{base_url}/products", params={"limit": 1})

    body = page.json()
    # The hidden product neither appears nor counts toward paging.
    assert [item["name"] for item in body["items"]] == ["Bình đun nước"]
    assert body["hasMore"] is True  # exactly `limit` rows came back


async def test_on_sale_filter_and_derived_fields(base_url):
    """?onSale=true returns only discounted items, with unit and the old
    price present so the card needs no second request."""
    token, _ = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/products",
            headers=auth(token),
            json={**PRODUCT, "name": "Hàng thường"},
        )
        await client.post(
            f"{base_url}/products",
            headers=auth(token),
            json={
                **PRODUCT,
                "name": "Hàng giảm giá",
                "unit": "Hộp 1 cái",
                "originalPrice": 500000,
            },
        )

        sale = await client.get(f"{base_url}/products", params={"onSale": "true"})
        everything = await client.get(f"{base_url}/products")

    items = sale.json()["items"]
    assert [item["name"] for item in items] == ["Hàng giảm giá"]
    assert items[0]["unit"] == "Hộp 1 cái"
    assert items[0]["originalPrice"] == 500000
    # The plain feed still carries both.
    assert len(everything.json()["items"]) == 2


async def test_sale_price_must_beat_current_price(base_url):
    token, _ = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/products",
            headers=auth(token),
            json={**PRODUCT, "originalPrice": PRODUCT["price"]},
        )

    assert response.status_code == 422


async def test_storefront_needs_no_token(base_url):
    token, shop_id = await seller_with_shop(base_url, USER_A_ID, "Shop A")

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/products", headers=auth(token), json=PRODUCT
        )
        response = await client.get(f"{base_url}/shops/{shop_id}/products")

    assert response.status_code == 200
    assert [p["name"] for p in response.json()["items"]] == ["Ấm siêu tốc"]


async def test_search_matches_product_or_shop_name(base_url):
    token_a, _ = await seller_with_shop(base_url, USER_A_ID, "Điện máy Sáng")
    token_b, _ = await seller_with_shop(base_url, USER_B_ID, "Thời trang Xanh")
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/products",
            headers=auth(token_a),
            json={"name": "Máy xay sinh tố", "description": ".", "price": 500000, "stock": 5},
        )
        await client.post(
            f"{base_url}/products",
            headers=auth(token_b),
            json={"name": "Áo khoác gió", "description": ".", "price": 300000, "stock": 5},
        )

        by_name = (
            await client.get(f"{base_url}/products", params={"q": "xay"})
        ).json()["items"]
        by_shop = (
            await client.get(f"{base_url}/products", params={"q": "Thời trang"})
        ).json()["items"]
        no_match = (
            await client.get(f"{base_url}/products", params={"q": "zzzzz"})
        ).json()["items"]
        # A LIKE wildcard from the user must match literally, not everything.
        literal = (
            await client.get(f"{base_url}/products", params={"q": "%"})
        ).json()["items"]

    assert [p["name"] for p in by_name] == ["Máy xay sinh tố"]
    assert [p["name"] for p in by_shop] == ["Áo khoác gió"]
    assert no_match == []
    assert literal == []
