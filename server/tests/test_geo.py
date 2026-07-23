"""Address helpers: the administrative-unit picker and reverse geocoding.

The picker is static data served one level at a time; reverse geocoding is
a call the MiniApp cannot make itself, so the server makes it. Only the
fallback path of reverse geocoding is covered here — the happy path needs a
live third-party provider, which the tests must not depend on.
"""

import httpx

from app.config import settings

HCM_CODE = "79"  # Thành phố Hồ Chí Minh
HCM_Q1_CODE = "760"  # Quận 1


async def test_provinces_lists_all_63(base_url):
    async with httpx.AsyncClient(base_url=base_url) as client:
        resp = await client.get("/geo/provinces")
    assert resp.status_code == 200
    provinces = resp.json()
    assert len(provinces) == 63
    assert any("Hồ Chí Minh" in p["name"] for p in provinces)
    assert all(p["code"] and p["name"] for p in provinces)


async def test_districts_and_wards_cascade(base_url):
    async with httpx.AsyncClient(base_url=base_url) as client:
        districts = (
            await client.get(f"/geo/districts?province={HCM_CODE}")
        ).json()
        wards = (
            await client.get(f"/geo/wards?district={HCM_Q1_CODE}")
        ).json()
    assert len(districts) == 22
    assert any(d["name"] == "Quận 1" for d in districts)
    assert wards and all(w["code"] and w["name"] for w in wards)


async def test_unknown_parent_returns_empty(base_url):
    async with httpx.AsyncClient(base_url=base_url) as client:
        resp = await client.get("/geo/districts?province=does-not-exist")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_reverse_geocode_falls_back_when_provider_down(
    base_url, monkeypatch
):
    # Point the geocoder at an unreachable host: the endpoint must still
    # answer — with no address — so checkout is never blocked by geocoding.
    monkeypatch.setattr(settings, "nominatim_base_url", "http://127.0.0.1:1")
    async with httpx.AsyncClient(base_url=base_url) as client:
        resp = await client.get("/geocode/reverse?lat=10.77&lng=106.70")
    assert resp.status_code == 200
    body = resp.json()
    assert body["address"] is None
    assert body["lat"] == 10.77
    assert body["lng"] == 106.70
