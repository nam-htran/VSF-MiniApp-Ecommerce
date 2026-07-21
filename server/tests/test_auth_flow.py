"""V-Market's login flow — not a contract test.

Checks the two rules from login-free-system:
  1. New user with scope 'auth' -> consent required, no account yet.
  2. Known user -> silent login, consent never shown again.

Plus one V-Market design rule:
  3. role / sellerId come from V-Market, not from V-App.
"""

import httpx
import pytest

from app.auth.tokens import verify_session_token
from app.config import settings
from tests.conftest import BUYER_ID, SELLER_A_ID

pytestmark = pytest.mark.skipif(
    "127.0.0.1" not in settings.vapp_base_url
    and "localhost" not in settings.vapp_base_url,
    reason="Needs the mock to mint authCodes on demand",
)


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
    body = await login(base_url, await auth_code_for(BUYER_ID, "auth"))

    assert body["status"] == "CONSENT_REQUIRED"
    assert "profile" in body["requiredScopes"]
    assert "token" not in body


async def test_account_is_created_after_consent(base_url):
    await login(base_url, await auth_code_for(BUYER_ID, "auth"))
    body = await login(base_url, await auth_code_for(BUYER_ID, "profile phone"))

    assert body["status"] == "AUTHENTICATED"
    assert body["token"]
    assert body["user"]["name"]


async def test_known_user_logs_in_silently(base_url):
    await login(base_url, await auth_code_for(BUYER_ID, "profile phone"))

    # Only scope 'auth' this time — that is the point of silent login.
    body = await login(base_url, await auth_code_for(BUYER_ID, "auth"))

    assert body["status"] == "AUTHENTICATED"
    assert body["token"]


async def test_role_and_seller_id_come_from_v_market(base_url):
    buyer = await login(base_url, await auth_code_for(BUYER_ID, "profile phone"))
    seller = await login(base_url, await auth_code_for(SELLER_A_ID, "profile phone"))

    assert buyer["user"]["role"] == "BUYER"
    assert buyer["user"]["sellerId"] is None

    assert seller["user"]["role"] == "SELLER"
    assert seller["user"]["sellerId"] == "seller-a"

    # Same facts must be in the JWT, for authorisation on later endpoints.
    claims = verify_session_token(seller["token"])
    assert claims.role == "SELLER"
    assert claims.seller_id == "seller-a"


async def test_bad_auth_code_returns_401(base_url):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/auth/session", json={"authCode": "ac_made-up"}
        )

    assert response.status_code == 401
    assert "token" not in response.json()
