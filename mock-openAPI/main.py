"""Mock of the V-App Open API."""

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

import store
from config import settings

app = FastAPI(
    title="V-App Open API (mock)",
    description="Mock of the V-App Open API.",
    version="0.1.0",
)

# 101xx are documented:
#   developer.v-app.vn/backend-api/open-api/error-codes
ERR_MISSING_AUTHORIZATION = 10101
ERR_INVALID_AUTHORIZATION_FORMAT = 10102
ERR_TOKEN_CHECK_FAILED = 10106
ERR_TOKEN_REVOKED_OR_EXPIRED = 10107
ERR_INTERNAL = 10701

# 102xx are invented — the docs don't publish authCode error codes.
# So callers must never branch on the specific number, only on code != 0.
ERR_INVALID_CLIENT = 10201
ERR_INVALID_AUTH_CODE = 10202
ERR_AUTH_CODE_EXPIRED = 10203
ERR_AUTH_CODE_ALREADY_USED = 10204
ERR_INVALID_REFRESH_TOKEN = 10205

_AUTH_CODE_ERRORS = {
    "not_found": (ERR_INVALID_AUTH_CODE, "Invalid auth_code"),
    "expired": (ERR_AUTH_CODE_EXPIRED, "auth_code has expired"),
    "already_used": (ERR_AUTH_CODE_ALREADY_USED, "auth_code has already been used"),
}


def ok(data) -> dict:
    # Open API wraps everything; code 0 means success, HTTP status alone
    # is not enough to tell.
    return {"code": 0, "message": "Success", "data": data}


def fail(http_status: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"code": code, "message": message, "data": None},
    )


def _client_ok(client_id, client_secret) -> bool:
    return (
        client_id == settings.client_id
        and client_secret == settings.client_secret
    )


def _token_response(user_id: str, scopes: list[str]) -> dict:
    access, refresh = store.issue_tokens(
        user_id, scopes, settings.access_token_ttl_seconds
    )
    return ok(
        {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "expires_in": settings.access_token_ttl_seconds,
            "scope": " ".join(scopes),
        }
    )


@app.post("/oauth2/token/exchange", tags=["Open API"])
async def exchange_token(request: Request):
    body = await request.json()

    if not _client_ok(body.get("client_id"), body.get("client_secret")):
        return fail(401, ERR_INVALID_CLIENT, "Invalid client_id or client_secret")

    auth_code = body.get("auth_code")
    if not auth_code:
        return fail(400, ERR_INVALID_AUTH_CODE, "Missing auth_code")

    result = store.consume_auth_code(auth_code)
    if isinstance(result, str):
        code, message = _AUTH_CODE_ERRORS[result]
        return fail(400, code, message)

    user_id, scopes = result
    return _token_response(user_id, scopes)


@app.post("/oauth2/token/refresh", tags=["Open API"])
async def refresh_token(request: Request):
    body = await request.json()

    if not _client_ok(body.get("client_id"), body.get("client_secret")):
        return fail(401, ERR_INVALID_CLIENT, "Invalid client_id or client_secret")

    token = body.get("refresh_token")
    if not token:
        return fail(400, ERR_INVALID_REFRESH_TOKEN, "Missing refresh_token")

    record = store.consume_refresh_token(token)
    if record is None:
        return fail(400, ERR_INVALID_REFRESH_TOKEN, "Invalid refresh_token")

    return _token_response(record.user_id, record.scopes)


@app.get("/open/identity/v1/userinfo", tags=["Open API"])
async def user_info(authorization: str | None = Header(default=None)):
    if authorization is None:
        return fail(401, ERR_MISSING_AUTHORIZATION, "Missing Authorization header")
    if not authorization.startswith("Bearer "):
        return fail(
            401,
            ERR_INVALID_AUTHORIZATION_FORMAT,
            'Authorization must start with "Bearer "',
        )

    result = store.lookup_access_token(authorization[len("Bearer ") :].strip())
    if isinstance(result, str):
        code = (
            ERR_TOKEN_REVOKED_OR_EXPIRED
            if result == "expired"
            else ERR_TOKEN_CHECK_FAILED
        )
        return fail(401, code, "Access token is invalid or expired")

    user_id, scopes = result
    user = store.find_user(user_id)
    if user is None:
        return fail(500, ERR_INTERNAL, "User not found")

    return ok(store.project_user_info(user, scopes))


# --- Demo controls: not part of the real V-App ------------------------
# These stand in for the getAuthCode JSAPI, which needs an appIdentifier
# registered in DevCenter.


@app.get("/simulator/users", tags=["Demo controls"])
async def simulator_users():
    return ok(
        [
            {"user_id": u.user_id, "name": u.name, "avatar_url": u.avatar_url}
            for u in store.SEED_USERS
        ]
    )


@app.post("/simulator/authcode", tags=["Demo controls"])
async def simulator_auth_code(request: Request):
    body = await request.json()
    user_id = body.get("user_id")

    if not user_id or store.find_user(user_id) is None:
        return fail(400, ERR_INVALID_AUTH_CODE, "Unknown user_id")

    granted = store.parse_scopes(body.get("scopes")) or ["auth"]
    auth_code = store.issue_auth_code(
        user_id, granted, settings.authcode_ttl_seconds
    )

    # Shape matches the getAuthCode success callback.
    return ok(
        {
            "authCode": auth_code,
            "authSuccessScopes": granted,
            "expires_in": settings.authcode_ttl_seconds,
        }
    )


@app.get("/healthz", tags=["System"])
async def healthz():
    return {"status": "ok"}
