"""Contract test — runs against whatever VAPP_BASE_URL points at.

    VAPP_BASE_URL=http://127.0.0.1:4001  pytest    # mock, today
    VAPP_BASE_URL=https://api.v-app.vn   pytest    # real, once credentialed

This is what turns "hopefully it plugs in" into "we know it does". On the
day credentials arrive, run the same command: all green means done, a red
test points at exactly what differs.

Against the real API an authCode can only come from a user tapping
consent on a device, so pass one via VAPP_TEST_AUTH_CODE. Since authCodes
are single use, only the first test can run that way; the rest skip.
"""

import os
import re

import httpx
import pytest

from app.config import settings
from app.vapp.errors import VAppApiError
from app.vapp.gateway import exchange_auth_code, get_user_info, refresh_token
from tests.conftest import BUYER_ID

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

# /simulator/* only exists on the mock.
HAS_SIMULATOR = "127.0.0.1" in settings.vapp_base_url or "localhost" in (
    settings.vapp_base_url
)
mock_only = pytest.mark.skipif(
    not HAS_SIMULATOR, reason="Needs the mock's /simulator endpoints"
)


async def issue_auth_code(scopes: str) -> str | None:
    if not HAS_SIMULATOR:
        return os.environ.get("VAPP_TEST_AUTH_CODE")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.vapp_base_url}/simulator/authcode",
            json={"user_id": BUYER_ID, "scopes": scopes},
        )
    body = response.json()
    assert body["code"] == 0
    return body["data"]["authCode"]


async def test_valid_auth_code_yields_token_and_user_id():
    auth_code = await issue_auth_code("auth")
    if not auth_code:
        pytest.skip("Real mode needs VAPP_TEST_AUTH_CODE")

    token = await exchange_auth_code(auth_code)
    assert token.access_token
    assert token.expires_in > 0

    info = await get_user_info(token.access_token)
    # A UUID, so nobody is tempted to parse it as an int.
    assert UUID_RE.match(info["user_id"])


@mock_only
async def test_auth_code_is_single_use():
    auth_code = await issue_auth_code("auth")
    await exchange_auth_code(auth_code)

    with pytest.raises(VAppApiError):
        await exchange_auth_code(auth_code)


@mock_only
async def test_unknown_auth_code_is_rejected():
    with pytest.raises(VAppApiError):
        await exchange_auth_code("ac_does-not-exist")


@mock_only
async def test_auth_scope_returns_only_user_id():
    token = await exchange_auth_code(await issue_auth_code("auth"))
    info = await get_user_info(token.access_token)

    # The most valuable assertion here. If the mock returned every field
    # regardless of scope, the backend would get used to always having
    # phone_number and break at checkout against the real API.
    assert info["user_id"]
    assert "name" not in info
    assert "phone_number" not in info
    assert "email" not in info


@mock_only
async def test_profile_phone_scope_returns_name_and_phone():
    token = await exchange_auth_code(await issue_auth_code("profile phone"))
    info = await get_user_info(token.access_token)

    assert info["name"]
    assert info["phone_number"]
    assert "email" not in info


@mock_only
async def test_refresh_returns_a_new_pair():
    first = await exchange_auth_code(await issue_auth_code("auth"))
    second = await refresh_token(first.refresh_token)

    assert second.access_token != first.access_token
    assert second.refresh_token != first.refresh_token

    info = await get_user_info(second.access_token)
    assert info["user_id"] == BUYER_ID


@mock_only
async def test_invalid_access_token_is_rejected():
    with pytest.raises(VAppApiError):
        await get_user_info("vat_not-a-real-token")


@mock_only
async def test_access_token_is_opaque():
    token = await exchange_auth_code(await issue_auth_code("auth"))

    # If user_id were encoded in the token, someone would decode it here
    # instead of calling userinfo, and that would break against the real API.
    assert BUYER_ID not in token.access_token
