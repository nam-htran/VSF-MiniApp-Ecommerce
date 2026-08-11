"""Who is calling, and are they allowed to.

Everything past login depends on this. AUTH-04 (a buyer calling a seller
endpoint) and AUTH-05 (a seller reaching another seller's data) are both
enforced here and in the route handlers — never in the UI alone.
"""

from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import verify_session_token
from app.db import get_session
from app.users import store as users
from app.users.store import MarketUser


async def current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> MarketUser:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    try:
        claims = verify_session_token(authorization[len("Bearer ") :].strip())
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None

    # Read the user back rather than trusting the token's copy: a role
    # revoked after the token was issued must take effect immediately.
    user = await users.find_by_id(session, claims.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user"
        )

    return user


CurrentUser = Annotated[MarketUser, Depends(current_user)]


async def optional_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> MarketUser | None:
    """Who is browsing, if anyone. A bad or missing token is an absence of a
    shopper, never a 401 — browsing must not fail on a credential."""
    if authorization is None or not authorization.startswith("Bearer "):
        return None
    try:
        return await current_user(session, authorization)
    except HTTPException:
        return None


OptionalUser = Annotated[MarketUser | None, Depends(optional_user)]


async def current_seller(user: CurrentUser) -> MarketUser:
    if user.role != "SELLER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seller role required",
        )
    return user


CurrentSeller = Annotated[MarketUser, Depends(current_seller)]


async def current_admin(user: CurrentUser) -> MarketUser:
    """Marketplace operator. Guards the money-reconciliation screens, which
    show gateway payment ids and amounts across every shop."""
    if user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


CurrentAdmin = Annotated[MarketUser, Depends(current_admin)]
