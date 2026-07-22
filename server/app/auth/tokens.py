"""V-Market's own session token.

The V-App access token never reaches the client — it stays on the server.
The client only ever holds this JWT.
"""

import time
from dataclasses import dataclass

import jwt

from app.config import settings
from app.users.store import MarketUser

_ALGORITHM = "HS256"


@dataclass(frozen=True)
class SessionClaims:
    sub: str
    role: str


def issue_session_token(user: MarketUser) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": user.id,
            "role": user.role,
            "iat": now,
            "exp": now + settings.jwt_ttl_seconds,
        },
        settings.jwt_secret,
        algorithm=_ALGORITHM,
    )


def verify_session_token(token: str) -> SessionClaims:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    return SessionClaims(sub=str(payload["sub"]), role=str(payload["role"]))
