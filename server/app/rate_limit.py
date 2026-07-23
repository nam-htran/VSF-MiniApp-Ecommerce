"""A blunt per-caller rate limit.

Review rule aside, an endpoint that creates orders or uploads files should
not be callable a thousand times a second by one account. This is the cheap
version: a fixed window counted in memory, keyed by the caller's token when
there is one and their IP otherwise.

In memory means it does not survive a restart and does not add up across
replicas. That is honest for a single-process demo and deliberately not
dressed up as more: a real deployment puts this in Redis, or in front of the
app entirely. What it does buy is that one runaway client cannot flood the
order table while somebody is watching the demo.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

# endpoint key -> caller -> timestamps inside the current window
_HITS: dict[str, dict[str, deque[float]]] = defaultdict(
    lambda: defaultdict(deque)
)


def _caller(request: Request) -> str:
    """Who is being limited: the session if there is one, else the address.

    The token, not the user id — this runs before authentication, and an
    unauthenticated flood is exactly what needs limiting.
    """
    authorization = request.headers.get("authorization")
    if authorization:
        return authorization[-32:]
    client = request.client
    return client.host if client else "unknown"


def limit(request: Request, bucket: str, times: int, seconds: float) -> None:
    """Allow `times` calls per `seconds` for this caller, or raise 429."""
    now = time.monotonic()
    hits = _HITS[bucket][_caller(request)]

    while hits and now - hits[0] > seconds:
        hits.popleft()

    if len(hits) >= times:
        retry_after = max(1, int(seconds - (now - hits[0])))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Bạn thao tác hơi nhanh, thử lại sau giây lát",
            headers={"Retry-After": str(retry_after)},
        )

    hits.append(now)


def reset() -> None:
    """Forget every window. For tests, which must not leak into each other."""
    _HITS.clear()
