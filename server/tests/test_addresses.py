"""The buyer's address book.

  the first address is the default, the next is not
  setting a default moves it; deleting the default promotes another
  addresses are owner-scoped — no reading or deleting someone else's
"""

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


@pytest_asyncio.fixture(autouse=True)
async def _empty(clean_db):
    yield


async def token_for(base_url: str, vapp_user_id: str) -> str:
    async with httpx.AsyncClient() as client:
        issued = await client.post(
            f"{settings.vapp_base_url}/simulator/authcode",
            json={"user_id": vapp_user_id, "scopes": "profile phone"},
        )
        auth_code = issued.json()["data"]["authCode"]
        session = await client.post(
            f"{base_url}/auth/session", json={"authCode": auth_code}
        )
    return session.json()["token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def addr(line: str) -> dict:
    return {
        "recipientName": "Nguyễn Văn A",
        "phone": "0900111222",
        "addressLine": line,
    }


async def test_first_address_is_default_second_is_not(base_url):
    token = await token_for(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        first = await client.post(
            f"{base_url}/addresses", headers=auth(token), json=addr("12 Lê Lợi, Q1, HCM")
        )
        second = await client.post(
            f"{base_url}/addresses", headers=auth(token), json=addr("5 Lê Duẩn, Q1, HCM")
        )
        rows = (await client.get(f"{base_url}/addresses", headers=auth(token))).json()

    assert first.status_code == 201 and first.json()["isDefault"] is True
    assert second.json()["isDefault"] is False
    # Default first in the listing.
    assert [r["isDefault"] for r in rows] == [True, False]


async def test_set_default_moves_it_and_delete_promotes_another(base_url):
    token = await token_for(base_url, USER_A_ID)
    async with httpx.AsyncClient() as client:
        first = (
            await client.post(
                f"{base_url}/addresses", headers=auth(token), json=addr("12 Lê Lợi, Q1, HCM")
            )
        ).json()
        second = (
            await client.post(
                f"{base_url}/addresses", headers=auth(token), json=addr("5 Lê Duẩn, Q1, HCM")
            )
        ).json()

        promoted = await client.post(
            f"{base_url}/addresses/{second['id']}/default", headers=auth(token)
        )
        assert promoted.status_code == 200 and promoted.json()["isDefault"] is True

        # Deleting the current default leaves the book with one that is now
        # the default, not one with no default at all.
        deleted = await client.delete(
            f"{base_url}/addresses/{second['id']}", headers=auth(token)
        )
        assert deleted.status_code == 204

        rows = (await client.get(f"{base_url}/addresses", headers=auth(token))).json()

    assert len(rows) == 1
    assert rows[0]["id"] == first["id"] and rows[0]["isDefault"] is True


async def test_addresses_are_owner_scoped(base_url):
    a_token = await token_for(base_url, USER_A_ID)
    b_token = await token_for(base_url, USER_B_ID)
    async with httpx.AsyncClient() as client:
        mine = (
            await client.post(
                f"{base_url}/addresses", headers=auth(a_token), json=addr("12 Lê Lợi, Q1, HCM")
            )
        ).json()

        b_sees = (await client.get(f"{base_url}/addresses", headers=auth(b_token))).json()
        b_deletes = await client.delete(
            f"{base_url}/addresses/{mine['id']}", headers=auth(b_token)
        )
        anon = await client.get(f"{base_url}/addresses")

    assert b_sees == []
    assert b_deletes.status_code == 404
    assert anon.status_code == 401
