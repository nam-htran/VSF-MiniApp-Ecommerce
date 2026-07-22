"""Login, following developer.v-app.vn/backend-api/resources/login-free-system

Two phases, and the split is the point:

  1. MiniApp calls getAuthCode(['auth']) — silent, no consent screen.
  2. Backend exchanges it for a user_id.
  3a. Known user  -> issue JWT. Returning users never see consent again.
  3b. New user    -> CONSENT_REQUIRED. MiniApp calls getAuthCode again with
      ['profile','phone'], which does show consent, then retries here.

So the consent screen appears exactly once per user, ever.
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import issue_session_token
from app.db import get_session
from app.users import store as users
from app.vapp.errors import VAppApiError
from app.vapp.gateway import exchange_auth_code, get_user_info

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auth"])

# V-Market needs a name and phone number for delivery.
PROFILE_SCOPES = ["profile", "phone"]


class SessionRequest(BaseModel):
    authCode: str


@router.post("/auth/session")
async def create_session(
    body: SessionRequest,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    try:
        token = await exchange_auth_code(body.authCode)
        info = await get_user_info(token.access_token)
    except VAppApiError as error:
        logger.warning(
            "authCode exchange failed: code=%s http=%s", error.code, error.http_status
        )
        return JSONResponse(
            status_code=401,
            content={
                "error": "VAPP_AUTH_FAILED",
                "message": "Could not authenticate with V-App",
            },
        )

    existing = await users.find_by_vapp_user_id(session, info["user_id"])
    if existing is not None:
        return JSONResponse(content=_authenticated(existing))

    # With scope 'auth' we only know the user_id — not enough to create an
    # account. Ask the MiniApp to collect consent and come back.
    if info.get("name") is None:
        return JSONResponse(
            content={"status": "CONSENT_REQUIRED", "requiredScopes": PROFILE_SCOPES}
        )

    created = await users.create_user(
        session,
        vapp_user_id=info["user_id"],
        name=info["name"],
        phone_number=info.get("phone_number"),
    )
    return JSONResponse(content=_authenticated(created))


def _authenticated(user: users.MarketUser) -> dict:
    return {
        "status": "AUTHENTICATED",
        "token": issue_session_token(user),
        "user": {"id": user.id, "role": user.role, "name": user.name},
    }
