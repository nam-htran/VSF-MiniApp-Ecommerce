"""Product image upload.

  a seller can upload an image and it is served back from our own origin
  a non-seller cannot upload (it would be a free file host otherwise)
  non-image content is rejected
"""

import base64

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from tests.conftest import USER_A_ID, USER_B_ID

pytestmark = pytest.mark.skipif(
    "127.0.0.1" not in settings.vapp_base_url
    and "localhost" not in settings.vapp_base_url,
    reason="Needs the mock to mint authCodes on demand",
)

# A 1x1 PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
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


async def seller_token(base_url: str, vapp_user_id: str) -> str:
    token = await token_for(base_url, vapp_user_id)
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{base_url}/shops",
            headers=auth(token),
            json={"name": "Shop", "description": "."},
        )
    return token


async def test_seller_uploads_and_image_is_served(base_url):
    token = await seller_token(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        uploaded = await client.post(
            f"{base_url}/uploads",
            headers=auth(token),
            files={"file": ("x.png", PNG, "image/png")},
        )
        assert uploaded.status_code == 200
        served = await client.get(uploaded.json()["url"])
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/")


async def test_non_seller_cannot_upload(base_url):
    token = await token_for(base_url, USER_B_ID)
    async with httpx.AsyncClient() as client:
        uploaded = await client.post(
            f"{base_url}/uploads",
            headers=auth(token),
            files={"file": ("x.png", PNG, "image/png")},
        )
    assert uploaded.status_code == 403


async def test_non_image_is_rejected(base_url):
    token = await seller_token(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        uploaded = await client.post(
            f"{base_url}/uploads",
            headers=auth(token),
            files={"file": ("x.txt", b"hello", "text/plain")},
        )
    assert uploaded.status_code == 400
