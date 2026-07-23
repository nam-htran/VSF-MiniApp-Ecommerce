"""Test matrix — the load rows.

  LOAD-01  a hundred readers on the storefront
  LOAD-02  twenty concurrent checkouts
  LOAD-03  climbing load until something gives

These are not benchmarks. They run against one uvicorn worker and one
Postgres container on a developer's laptop, so the numbers mean nothing
about production capacity — a real load test needs its own environment,
which the matrix itself says. What they do check is the thing a laptop can
honestly answer: under concurrency the system stays *correct* and keeps
answering, rather than corrupting data or falling over.

Marked `slow`; run the rest of the suite without them with

    pytest -m "not slow"
"""

import asyncio
import time

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from tests.conftest import USER_A_ID, USER_B_ID

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        "127.0.0.1" not in settings.vapp_base_url
        and "localhost" not in settings.vapp_base_url,
        reason="Needs the mock to mint authCodes on demand",
    ),
]


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


async def stocked_shop(base_url: str, products: int, stock: int) -> list[str]:
    """A shop with `products` items, each holding `stock`."""
    seller = await token_for(base_url, USER_B_ID)
    ids = []
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(seller),
            json={"name": "Shop tải", "description": "."},
        )
        for index in range(products):
            created = await client.post(
                f"{base_url}/products",
                headers=auth(seller),
                json={
                    "name": f"Hàng tải {index}",
                    "description": ".",
                    "price": 100_000,
                    "stock": stock,
                },
            )
            ids.append(created.json()["id"])
    return ids


# --- LOAD-01 ---------------------------------------------------------------


async def test_load_01_a_hundred_readers_on_the_storefront(base_url):
    await stocked_shop(base_url, products=12, stock=50)

    async with httpx.AsyncClient(
        timeout=30, limits=httpx.Limits(max_connections=50)
    ) as client:
        started = time.monotonic()
        responses = await asyncio.gather(
            *[client.get(f"{base_url}/products?limit=20") for _ in range(100)],
            return_exceptions=True,
        )
        elapsed = time.monotonic() - started

    failures = [r for r in responses if isinstance(r, Exception)]
    codes = [r.status_code for r in responses if not isinstance(r, Exception)]
    print(f"\n  LOAD-01: 100 reads in {elapsed:.1f}s, {codes.count(200)} ok")

    assert not failures, f"{len(failures)} request(s) never completed"
    assert codes.count(200) == 100
    # Browsing is public and unthrottled, so nothing should be turned away.
    assert 429 not in codes


# --- LOAD-02 ---------------------------------------------------------------


async def test_load_02_twenty_concurrent_checkouts(base_url):
    """Twenty buyers, twenty units, one product: every unit sells exactly
    once and the stock lands on nought."""
    [product] = await stocked_shop(base_url, products=1, stock=20)
    # One session, twenty simultaneous checkouts — the shape of a flash sale
    # from a single account. Fetched once rather than twenty times in
    # parallel: minting tokens is setup, and hammering the mock for them was
    # timing out before the thing under test even started.
    #
    # Twenty is also exactly the per-caller allowance, so the limiter lets
    # them all through and what is measured is the stock lock, not the
    # throttle.
    token = await token_for(base_url, USER_A_ID)
    buyers = [token] * 20

    async with httpx.AsyncClient(
        timeout=240, limits=httpx.Limits(max_connections=30)
    ) as client:
        started = time.monotonic()
        responses = await asyncio.gather(
            *[
                client.post(
                    f"{base_url}/orders",
                    headers=auth(token),
                    json={
                        "address": ADDRESS,
                        "items": [{"productId": product, "qty": 1}],
                    },
                )
                for token in buyers
            ],
            return_exceptions=True,
        )
        elapsed = time.monotonic() - started
        after = (await client.get(f"{base_url}/products/{product}")).json()

    failures = [r for r in responses if isinstance(r, Exception)]
    created = [r for r in responses if not isinstance(r, Exception) and r.status_code == 201]
    order_ids = {r.json()["id"] for r in created}
    print(
        f"\n  LOAD-02: 20 checkouts in {elapsed:.1f}s, "
        f"{len(created)} orders, stock left {after['stock']}"
    )

    assert not failures, f"{len(failures)} request(s) never completed"
    # No duplicated orders, no oversell, no stock left unaccounted for.
    assert len(order_ids) == len(created)
    assert after["stock"] == 20 - len(created)
    assert after["stock"] >= 0


# --- LOAD-03 ---------------------------------------------------------------


@pytest.mark.parametrize("users", [10, 25, 50])
async def test_load_03_climbing_read_load_stays_correct(base_url, users):
    """Step the read load up and record what happens at each rung.

    The pass condition is correctness and completion, not a latency target:
    on this hardware a threshold would only measure the laptop.
    """
    await stocked_shop(base_url, products=6, stock=30)

    async with httpx.AsyncClient(
        timeout=60, limits=httpx.Limits(max_connections=users)
    ) as client:
        started = time.monotonic()
        responses = await asyncio.gather(
            *[client.get(f"{base_url}/products?limit=20") for _ in range(users)],
            return_exceptions=True,
        )
        elapsed = time.monotonic() - started

    failures = [r for r in responses if isinstance(r, Exception)]
    ok = [r for r in responses if not isinstance(r, Exception) and r.status_code == 200]
    per_request = elapsed / users if users else 0
    print(
        f"\n  LOAD-03 @{users:>3} users: {elapsed:.1f}s total, "
        f"{per_request * 1000:.0f}ms/request, {len(ok)}/{users} ok"
    )

    assert not failures
    assert len(ok) == users
    # Every response is a real page, not a truncated or empty body.
    assert all(len(r.json()["items"]) > 0 for r in ok)
