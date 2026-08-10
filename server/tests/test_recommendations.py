"""The "for you" strip.

  recommendations need a session — there is nobody to personalise for
  a shopper with no history gets best sellers, and is told so
  a viewed product pulls in others sharing its Semantic ID
  what you just looked at is never recommended back to you
  the closer Semantic ID wins
  a view of a product that does not exist is refused
"""

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.products import store as products
from app.recommendations.semantic_indexer import build_product_text
from tests.conftest import USER_A_ID, USER_B_ID, _throwaway_engine

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


async def seller_with_products(base_url: str, names: list[str]) -> list[str]:
    token = await token_for(base_url, USER_A_ID)
    ids = []
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": "Shop A", "description": "."},
        )
        for name in names:
            created = await client.post(
                f"{base_url}/products",
                headers=auth(token),
                json={"name": name, "description": ".", "price": 100000, "stock": 10},
            )
            ids.append(created.json()["id"])
    return ids


async def set_semantic_id(product_id: str, sid: tuple[int, int, int]) -> None:
    """Semantic IDs come from the model pipeline, so no endpoint accepts
    one — the seed writes them straight to the row and so does this."""
    engine = _throwaway_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE products SET sid_0 = :a, sid_1 = :b, sid_2 = :c"
                " WHERE id = :id"
            ),
            {"id": product_id, "a": sid[0], "b": sid[1], "c": sid[2]},
        )
    await engine.dispose()


async def semantic_id(product_id: str) -> tuple[int | None, int | None, int | None]:
    engine = _throwaway_engine()
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT sid_0, sid_1, sid_2 FROM products WHERE id = :id"
                ),
                {"id": product_id},
            )
        ).one()
    await engine.dispose()
    return tuple(row)


async def recommendations(base_url: str, token: str, limit: int = 10) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/recommendations?limit={limit}", headers=auth(token)
        )
    return response.json()


async def related(base_url: str, product_id: str, limit: int = 10) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/products/{product_id}/related?limit={limit}"
        )
    return response.json()


async def view(base_url: str, token: str, product_id: str) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.post(
            f"{base_url}/products/{product_id}/view", headers=auth(token)
        )


def test_semantic_text_matches_the_training_contract():
    assert build_product_text("  Áo\tlen  ", "Mềm\n và ấm") == (
        "title: Áo len | description: Mềm và ấm"
    )


async def test_only_semantic_edits_clear_an_existing_sid(base_url):
    product_id = (await seller_with_products(base_url, ["Bàn phím"]))[0]
    await set_semantic_id(product_id, (7, 6, 5))
    seller = await token_for(base_url, USER_A_ID)

    async with httpx.AsyncClient() as client:
        price_edit = await client.patch(
            f"{base_url}/products/{product_id}",
            headers=auth(seller),
            json={"price": 120000},
        )
        assert price_edit.status_code == 200
        assert await semantic_id(product_id) == (7, 6, 5)

        text_edit = await client.patch(
            f"{base_url}/products/{product_id}",
            headers=auth(seller),
            json={"description": "Bàn phím cơ không dây"},
        )
        assert text_edit.status_code == 200
        assert await semantic_id(product_id) == (None, None, None)


async def test_stale_semantic_result_cannot_overwrite_new_text(base_url):
    product_id = (await seller_with_products(base_url, ["Tai nghe"]))[0]
    engine = _throwaway_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        old = (await products.pending_semantic_products(session, limit=1))[0]

    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE products SET description = :text WHERE id = :id"),
            {"id": product_id, "text": "Nội dung seller vừa sửa"},
        )

    async with sessions() as session:
        written = await products.write_semantic_ids(
            session, [(old, (7, 6, 5))]
        )

    assert written == 0
    assert await semantic_id(product_id) == (None, None, None)
    await engine.dispose()


async def test_beam_catalogue_contains_only_complete_active_sids(base_url):
    active, hidden, _pending = await seller_with_products(
        base_url, ["Active", "Hidden", "Pending"]
    )
    await set_semantic_id(active, (7, 6, 5))
    await set_semantic_id(hidden, (12, 1, 4))
    seller = await token_for(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{base_url}/products/{hidden}",
            headers=auth(seller),
            json={"status": "HIDDEN"},
        )
    assert response.status_code == 200

    engine = _throwaway_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        catalogue = await products.active_semantic_ids(session)
    await engine.dispose()

    assert set(catalogue) == {(7, 6, 5)}


async def test_recommendations_need_a_session(base_url):
    async with httpx.AsyncClient() as client:
        anonymous = await client.get(f"{base_url}/recommendations")
    assert anonymous.status_code == 401


async def test_no_history_falls_back_to_best_sellers(base_url):
    await seller_with_products(base_url, ["Bàn phím", "Chuột"])
    buyer = await token_for(base_url, USER_B_ID)

    body = await recommendations(base_url, buyer)

    # Named honestly: nothing here came from this shopper's behaviour.
    assert body["source"] == "popular"
    assert len(body["items"]) == 2


async def test_a_view_pulls_in_products_sharing_its_semantic_id(base_url):
    seen, sibling, stranger = await seller_with_products(
        base_url, ["Ibuprofen 400", "Ibuprofen 600", "Bàn phím cơ"]
    )
    await set_semantic_id(seen, (7, 7, 7))
    await set_semantic_id(sibling, (7, 7, 7))
    await set_semantic_id(stranger, (200, 1, 1))
    buyer = await token_for(base_url, USER_B_ID)

    assert (await view(base_url, buyer, seen)).status_code == 204
    body = await recommendations(base_url, buyer)

    assert body["source"] == "semantic-id"
    returned = [item["id"] for item in body["items"]]
    # The sibling leads: it shares all three codes. The unrelated product
    # may still appear behind it as filler, but never ahead.
    assert returned[0] == sibling
    # And what they just looked at is not recommended back to them.
    assert seen not in returned


async def test_a_closer_semantic_id_ranks_higher(base_url):
    seen, near, far = await seller_with_products(
        base_url, ["Đã xem", "Cùng cụm", "Cùng nhánh"]
    )
    await set_semantic_id(seen, (9, 9, 9))
    # Same three codes — one cluster.
    await set_semantic_id(near, (9, 9, 9))
    # Shares only the coarse code, so a broad resemblance and no more.
    await set_semantic_id(far, (9, 200, 200))
    buyer = await token_for(base_url, USER_B_ID)

    await view(base_url, buyer, seen)
    body = await recommendations(base_url, buyer)

    assert [item["id"] for item in body["items"]][:2] == [near, far]


async def test_transformer_beam_drives_home_recommendations(base_url, monkeypatch):
    from app.recommendations.predictor import Prediction

    seen, exact, wider = await seller_with_products(
        base_url, ["Đã xem", "Dự đoán chính xác", "Cùng nhánh dự đoán"]
    )
    await set_semantic_id(seen, (9, 9, 9))
    await set_semantic_id(exact, (7, 6, 5))
    await set_semantic_id(wider, (7, 6, 4))
    buyer = await token_for(base_url, USER_B_ID)

    async def predict(history):
        assert history == [(9, 9, 9), (9, 9, 9)]
        return [Prediction((7, 6, 5), -0.1)]

    monkeypatch.setattr("app.recommendations.predictor.predict", predict)
    await view(base_url, buyer, seen)
    await view(base_url, buyer, seen)
    body = await recommendations(base_url, buyer)

    assert body["source"] == "transformer"
    assert [item["id"] for item in body["items"]][:2] == [exact, wider]


async def test_product_detail_related_backs_off_by_sid_level(base_url):
    current, exact, level_two, level_one = await seller_with_products(
        base_url, ["Hiện tại", "Cùng cụm", "Cùng nhánh", "Cùng ngành"]
    )
    await set_semantic_id(current, (9, 8, 7))
    await set_semantic_id(exact, (9, 8, 7))
    await set_semantic_id(level_two, (9, 8, 6))
    await set_semantic_id(level_one, (9, 1, 1))

    body = await related(base_url, current, limit=3)

    assert [item["id"] for item in body["items"]] == [
        exact,
        level_two,
        level_one,
    ]


async def test_viewing_a_product_that_does_not_exist_is_refused(base_url):
    buyer = await token_for(base_url, USER_B_ID)
    missing = await view(base_url, buyer, "00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
