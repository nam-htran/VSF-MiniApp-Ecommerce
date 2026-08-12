"""The storefront ranking, which is where recommendations are served.

  the storefront serves a visitor with no session — browsing never 401s
  a shopper with no history gets best sellers, and rankedBy says so
  a viewed product pulls in others sharing its Semantic ID
  what you just looked at is never recommended back to you
  the closer Semantic ID wins
  a view of a product that does not exist is refused
  a view reorders the storefront itself, and only for the shopper who made it
  the storefront backs off through all three Semantic ID levels
  a visitor with no account is recommended to, from history they send
  one ranking serves a whole anonymous walk
  a view ends the cached ranking that holds a storefront walk together
"""

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.products import store as products
from app.recommendations import store as recommendations_store
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
    """The storefront feed, which is where recommendations are served.

    Unlike the strip this replaced, the feed is the whole catalogue: products
    the ranking leaves out are not missing, they are behind everything it
    named.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/products?limit={limit}", headers=auth(token)
        )
    body = response.json()
    return {"items": body["items"], "source": body["rankedBy"]}


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


async def test_the_storefront_serves_a_visitor_with_no_session(base_url):
    """Browsing must never fail on a credential. Recommendations moved into
    the storefront feed, so the feed has to stay public — a bad or missing
    token is a shopper the ranking knows nothing about, not a 401."""
    await seller_with_products(base_url, ["Bàn phím"])

    async with httpx.AsyncClient() as client:
        anonymous = await client.get(f"{base_url}/products")
        rubbish = await client.get(
            f"{base_url}/products", headers=auth("not-a-token")
        )

    assert anonymous.status_code == 200
    assert rubbish.status_code == 200
    # Nothing personalised the order, and the feed says so rather than
    # implying a shopper it never had.
    assert anonymous.json()["rankedBy"] is None
    assert rubbish.json()["rankedBy"] is None


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
    # may still appear behind it, but never ahead.
    assert returned[0] == sibling
    # What they just looked at is left out of the ranking — not promoted,
    # not buried either. A feed still stocks the whole marketplace.
    assert set(returned) == {seen, sibling, stranger}


async def test_a_closer_semantic_id_ranks_higher(base_url):
    seen, near, far = await seller_with_products(
        base_url, ["Đã xem", "Cùng cụm", "Cùng nhánh"]
    )
    await set_semantic_id(seen, (9, 9, 9))
    # Same three codes — one cluster.
    await set_semantic_id(near, (9, 9, 9))
    # Shares the first two, so the same branch but not the same cluster.
    await set_semantic_id(far, (9, 9, 8))
    buyer = await token_for(base_url, USER_B_ID)

    await view(base_url, buyer, seen)
    body = await recommendations(base_url, buyer)

    # Depth decides: three codes shared beats two. Both are ranked, so this
    # is the ordering itself rather than one of them arriving as filler.
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


async def test_transformer_does_not_fill_the_screen_from_one_cluster(
    base_url, monkeypatch
):
    from app.recommendations.predictor import Prediction

    seen, exact_a, exact_b, exact_c, wider = await seller_with_products(
        base_url, ["Đã xem", "Exact A", "Exact B", "Exact C", "Cùng nhánh"]
    )
    await set_semantic_id(seen, (9, 9, 9))
    for product_id in (exact_a, exact_b, exact_c):
        await set_semantic_id(product_id, (7, 6, 5))
    await set_semantic_id(wider, (7, 6, 4))
    buyer = await token_for(base_url, USER_B_ID)

    async def predict(history):
        return [Prediction((7, 6, 5), -0.1)]

    monkeypatch.setattr("app.recommendations.predictor.predict", predict)
    await view(base_url, buyer, seen)
    body = await recommendations(base_url, buyer)
    first_ids = [item["id"] for item in body["items"][:2]]

    assert first_ids[0] in {exact_a, exact_b, exact_c}
    assert first_ids[1] == wider


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


async def storefront(base_url: str, token: str | None = None) -> list[str]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/products?limit=50",
            headers=auth(token) if token else None,
        )
    return [item["name"] for item in response.json()["items"]]


async def test_a_view_reorders_the_storefront_itself(base_url):
    """The feed is the recommendation — there is no strip to put it in."""
    names = ["Alpha", "Alpha kèm", "Beta", "Beta kèm"]
    ids = await seller_with_products(base_url, names)
    alpha, alpha_pair, beta, beta_pair = ids
    await set_semantic_id(alpha, (1, 1, 1))
    await set_semantic_id(alpha_pair, (1, 1, 1))
    await set_semantic_id(beta, (9, 9, 9))
    await set_semantic_id(beta_pair, (9, 9, 9))

    shopper = await token_for(base_url, USER_B_ID)
    # Nothing sold and nothing rated, so the order falls to its last
    # tiebreak, the product id.
    window = [name for _, name in sorted(zip(ids, names))]
    assert await storefront(base_url) == window
    assert await storefront(base_url, shopper) == window

    await view(base_url, shopper, beta)

    ranked = await storefront(base_url, shopper)
    # The viewed product's cluster mate leads; the rest of the marketplace
    # is still all there, behind it.
    assert ranked[0] == "Beta kèm"
    assert sorted(ranked) == sorted(names)
    assert await storefront(base_url) == window


async def test_the_storefront_backs_off_through_all_three_sid_levels(base_url):
    """Deepest prefix first, then the next, then the coarse one.

    Sharing only the first code is a weak signal, but it is still about this
    shopper — weaker than a cluster match and better than the units-sold
    order the feed would otherwise fall to.
    """
    seen, near, mid, far, unrelated = await seller_with_products(
        base_url, ["Đã xem", "Cùng cụm", "Cùng nhánh", "Cùng ngành", "Không liên quan"]
    )
    await set_semantic_id(seen, (9, 9, 9))
    await set_semantic_id(near, (9, 9, 9))
    await set_semantic_id(mid, (9, 9, 8))
    await set_semantic_id(far, (9, 1, 1))
    await set_semantic_id(unrelated, (200, 1, 1))
    buyer = await token_for(base_url, USER_B_ID)

    await view(base_url, buyer, seen)
    body = await recommendations(base_url, buyer)

    assert [item["id"] for item in body["items"]][:3] == [near, mid, far]
    # Nothing shares a code with the history, so nothing ranks it.
    assert unrelated not in [item["id"] for item in body["items"]][:3]


async def test_one_ranking_serves_a_whole_anonymous_walk(base_url):
    """The Transformer runs once per storefront load, not once per page.

    The feed is scrolled through a page at a time, and every page carries
    the same history — recomputing per page would spend the model on an
    answer already given.
    """
    seen, sibling = await seller_with_products(base_url, ["Ibuprofen", "Ibuprofen 600"])
    await set_semantic_id(seen, (7, 7, 7))
    await set_semantic_id(sibling, (7, 7, 7))
    recommendations_store._last_anonymous = None

    async with httpx.AsyncClient() as client:
        first = await client.get(f"{base_url}/products?limit=1&seen={seen}")
        held = recommendations_store._last_anonymous
        # The next page of the same walk: same history, so the held ranking
        # answers it rather than the model.
        await client.get(f"{base_url}/products?limit=1&offset=1&seen={seen}")

    assert first.json()["rankedBy"] == "semantic-id"
    assert held is not None
    assert held[0] == (seen,)
    assert recommendations_store._last_anonymous is held

    # A different history is a different walk, and replaces it.
    async with httpx.AsyncClient() as client:
        await client.get(f"{base_url}/products?seen={sibling}")
    assert recommendations_store._last_anonymous[0] == (sibling,)


async def test_a_visitor_with_no_account_is_recommended_to(base_url):
    """The history arrives with the request instead of being looked up.

    Signing in cannot be the price of a useful storefront: most visitors
    never do, and the ranking works the same either way.
    """
    seen, sibling, stranger = await seller_with_products(
        base_url, ["Ibuprofen 400", "Ibuprofen 600", "Bàn phím cơ"]
    )
    await set_semantic_id(seen, (7, 7, 7))
    await set_semantic_id(sibling, (7, 7, 7))
    await set_semantic_id(stranger, (200, 1, 1))

    async with httpx.AsyncClient() as client:
        # No token anywhere — only what the device says it has been looking at.
        ranked = (
            await client.get(f"{base_url}/products?limit=10&seen={seen}")
        ).json()

    assert ranked["rankedBy"] == "semantic-id"
    returned = [item["id"] for item in ranked["items"]]
    assert returned[0] == sibling
    assert set(returned) == {seen, sibling, stranger}

    # And nothing about that visitor was written down.
    engine = _throwaway_engine()
    async with engine.connect() as conn:
        recorded = await conn.scalar(text("SELECT count(*) FROM product_views"))
    await engine.dispose()
    assert recorded == 0


async def test_a_visitor_sending_nothing_gets_the_plain_shop_window(base_url):
    await seller_with_products(base_url, ["Bàn phím", "Chuột"])

    async with httpx.AsyncClient() as client:
        empty = (await client.get(f"{base_url}/products?seen=")).json()
        junk = (await client.get(f"{base_url}/products?seen=,,%20,")).json()

    # Nothing to rank from is not the same as ranked and found nothing.
    assert empty["rankedBy"] is None
    assert junk["rankedBy"] is None
    assert len(empty["items"]) == 2


async def test_a_view_forgets_the_cached_ranking(base_url):
    """Asserted against the cache itself: over HTTP a stale ranking and a
    fresh one list the same products until the catalogue is big enough to
    disagree."""
    chair, desk = await seller_with_products(base_url, ["Ghế", "Bàn"])
    # Without these there is nothing to rank from: a view of a product the
    # RQ-VAE has not reached yet tells the model nothing.
    await set_semantic_id(chair, (4, 4, 4))
    await set_semantic_id(desk, (4, 4, 4))
    shopper = await token_for(base_url, USER_B_ID)
    # Entries outlive the truncation between tests.
    recommendations_store._rankings.clear()

    # Nothing viewed yet, so there is nothing to rank and nothing to hold.
    await storefront(base_url, shopper)
    assert not recommendations_store._rankings

    await view(base_url, shopper, chair)
    await storefront(base_url, shopper)
    assert recommendations_store._rankings, "the walk should have been cached"

    await view(base_url, shopper, desk)
    assert not recommendations_store._rankings
