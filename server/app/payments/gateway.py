"""Talking to the payment gateway from the server, not the browser.

Opening the session here rather than in the MiniApp is what lets the rest
of the system know a payment is in flight: the order records the session id
and stops being treated as an abandoned basket. It also means the merchant
can *ask* the gateway what happened, which is the only defence against a
webhook that never arrives.
"""

import httpx

from app.config import settings


async def open_session(order_id: str, amount: int) -> dict:
    """Start a payment. Returns the gateway's session, or raises."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.vapp_base_url}/simulator/payment/init",
            json={"orderId": order_id, "amount": amount},
        )
    response.raise_for_status()
    return response.json()["data"]


async def query(payment_id: str) -> dict | None:
    """What the gateway believes about a payment, or None if unknown.

    Network trouble returns None too: "we could not ask" and "it does not
    exist" both mean *do not change the order*, which is the safe reading.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.vapp_base_url}/simulator/payment/{payment_id}"
            )
        if response.status_code != 200:
            return None
        return response.json()["data"]
    except httpx.HTTPError:
        return None
