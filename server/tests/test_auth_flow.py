"""V-Market's login flow — not a contract test.

Checks the two rules from login-free-system:
  1. New user with scope 'auth' -> consent required, no account yet.
  2. Known user -> silent login, consent never shown again.

Plus one V-Market design rule:
  3. role comes from V-Market, not from V-App.
"""

import httpx
import pytest
import pytest_asyncio

from app.auth.tokens import verify_session_token
from app.config import settings
from tests.conftest import USER_A_ID, USER_B_ID

pytestmark = pytest.mark.skipif(
    "127.0.0.1" not in settings.vapp_base_url
    and "localhost" not in settings.vapp_base_url,
    reason="Needs the mock to mint authCodes on demand",
)


# These tests do hit the database, unlike the contract tests.
@pytest_asyncio.fixture(autouse=True)
async def _empty(clean_db):
    yield


async def auth_code_for(user_id: str, scopes: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.vapp_base_url}/simulator/authcode",
            json={"user_id": user_id, "scopes": scopes},
        )
    return response.json()["data"]["authCode"]


async def login(base_url: str, auth_code: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/auth/session", json={"authCode": auth_code}
        )
    return response.json()


async def test_new_user_with_auth_scope_needs_consent(base_url):
    body = await login(base_url, await auth_code_for(USER_A_ID, "auth"))

    assert body["status"] == "CONSENT_REQUIRED"
    assert "profile" in body["requiredScopes"]
    assert "token" not in body


async def test_account_is_created_after_consent(base_url):
    await login(base_url, await auth_code_for(USER_A_ID, "auth"))
    body = await login(base_url, await auth_code_for(USER_A_ID, "profile phone"))

    assert body["status"] == "AUTHENTICATED"
    assert body["token"]
    assert body["user"]["name"]


async def test_known_user_logs_in_silently(base_url):
    await login(base_url, await auth_code_for(USER_A_ID, "profile phone"))

    # Only scope 'auth' this time — that is the point of silent login.
    body = await login(base_url, await auth_code_for(USER_A_ID, "auth"))

    assert body["status"] == "AUTHENTICATED"
    assert body["token"]


async def test_role_comes_from_v_market(base_url):
    a = await login(base_url, await auth_code_for(USER_A_ID, "profile phone"))
    b = await login(base_url, await auth_code_for(USER_B_ID, "profile phone"))

    # V-App hands out identities only. Nobody arrives privileged — a seller
    # is made by opening a shop, see test_shops.py.
    assert a["user"]["role"] == "BUYER"
    assert b["user"]["role"] == "BUYER"

    # Same fact must be in the JWT, for authorisation on later endpoints.
    assert verify_session_token(a["token"]).role == "BUYER"


async def test_an_account_registered_just_now_can_log_in(base_url):
    """Accounts are not a fixed list — V-App can grow new ones."""
    async with httpx.AsyncClient() as client:
        registered = await client.post(
            f"{settings.vapp_base_url}/simulator/users",
            json={"name": "Phạm Minh Đức"},
        )
    user_id = registered.json()["data"]["user_id"]

    body = await login(base_url, await auth_code_for(user_id, "profile phone"))

    assert body["status"] == "AUTHENTICATED"
    assert body["user"]["name"] == "Phạm Minh Đức"
    assert body["user"]["role"] == "BUYER"


async def test_bad_auth_code_returns_401(base_url):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/auth/session", json={"authCode": "ac_made-up"}
        )

    assert response.status_code == 401
    assert "token" not in response.json()
