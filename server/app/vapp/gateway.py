"""The only place that talks to the V-App Open API.

There is a single implementation. Running against the mock or against the
real API differs only by VAPP_BASE_URL — no branching here.

Keeping two parallel implementations would be the trap: the mock one gets
exercised daily and stays correct, the real one never runs and rots, and
that only shows up on the day you need it.
"""

from dataclasses import dataclass

import httpx

from app.config import settings
from app.vapp.errors import VAppApiError

_TIMEOUT = httpx.Timeout(10.0)


@dataclass(frozen=True)
class VAppToken:
    access_token: str
    refresh_token: str
    expires_in: int
    scopes: list[str]


def _url(path: str) -> str:
    return f"{settings.vapp_base_url.rstrip('/')}{path}"


def _unwrap(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise VAppApiError(
            -1,
            f"Response was not JSON (HTTP {response.status_code})",
            response.status_code,
        ) from exc

    if not isinstance(body, dict) or not isinstance(body.get("code"), int):
        raise VAppApiError(-1, 'Response has no "code" field', response.status_code)

    # Branch on code, never on the specific number: the mock's authCode
    # error codes are invented and the real ones are undocumented.
    if body["code"] != 0:
        raise VAppApiError(
            body["code"], str(body.get("message", "")), response.status_code
        )

    return body.get("data") or {}


def _to_token(data: dict) -> VAppToken:
    return VAppToken(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_in=int(data["expires_in"]),
        scopes=str(data.get("scope", "")).split(),
    )


async def exchange_auth_code(auth_code: str) -> VAppToken:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            _url("/oauth2/token/exchange"),
            json={
                "client_id": settings.vapp_client_id,
                "client_secret": settings.vapp_client_secret,
                "auth_code": auth_code,
            },
        )
    return _to_token(_unwrap(response))


async def refresh_token(token: str) -> VAppToken:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            _url("/oauth2/token/refresh"),
            json={
                "client_id": settings.vapp_client_id,
                "client_secret": settings.vapp_client_secret,
                "refresh_token": token,
            },
        )
    return _to_token(_unwrap(response))


async def get_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(
            _url("/open/identity/v1/userinfo"),
            headers={"Authorization": f"Bearer {access_token}"},
        )
    return _unwrap(response)
