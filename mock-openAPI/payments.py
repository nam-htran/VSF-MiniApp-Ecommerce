"""Payment gateway simulation.

Stands in for the part of V-App that `initPayment` would reach: it holds a
payment session, and on confirmation it notifies the merchant (server/)
server-to-server with a signed IPN — retrying on a backoff until the
merchant answers 200, exactly as a real gateway does when the shop is
briefly unreachable.

Sessions live in memory: the mock is a dev stand-in and a payment is
short-lived, so there is nothing to persist.
"""

import asyncio
import hashlib
import hmac
import logging
import uuid

import httpx

from config import settings

logger = logging.getLogger("mock.payments")

# paymentId -> {"orderId", "amount", "status"}
_payments: dict[str, dict] = {}


def create_session(order_id: str, amount: int) -> str:
    payment_id = f"pay_{uuid.uuid4().hex[:16]}"
    _payments[payment_id] = {
        "orderId": order_id,
        "amount": amount,
        "status": "PENDING",
    }
    return payment_id


def _signature(order_id: str, amount: int, status: str) -> str:
    message = f"{order_id}|{amount}|{status}".encode()
    return hmac.new(
        settings.payment_ipn_secret.encode(), message, hashlib.sha256
    ).hexdigest()


async def _attempt_ipn(payment_id: str, order_id: str, amount: int) -> bool:
    payload = {
        "paymentId": payment_id,
        "orderId": order_id,
        "amount": amount,
        "status": "PAID",
        "secureHash": _signature(order_id, amount, "PAID"),
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(settings.merchant_ipn_url, json=payload)
        return response.status_code == 200
    except httpx.HTTPError as error:
        logger.warning("IPN attempt failed for %s: %s", order_id, error)
        return False


async def _retry_ipn(payment_id: str, order_id: str, amount: int) -> None:
    for delay in settings.ipn_retry_delays:
        await asyncio.sleep(delay)
        if await _attempt_ipn(payment_id, order_id, amount):
            logger.info("IPN delivered on retry for %s", order_id)
            return
    logger.error("IPN gave up for %s after retries", order_id)


async def confirm(payment_id: str) -> dict | None:
    """Mark a session paid and notify the merchant.

    The first IPN attempt runs inline so the happy path is settled by the
    time this returns; if the merchant is down, the retries run in the
    background and confirm still returns (payment succeeded on the gateway
    regardless of whether the shop has heard yet)."""
    payment = _payments.get(payment_id)
    if payment is None:
        return None
    if payment["status"] == "PAID":
        return {"status": "PAID", "ipnDelivered": True}

    delivered = await _attempt_ipn(
        payment_id, payment["orderId"], payment["amount"]
    )
    payment["status"] = "PAID"
    if not delivered:
        asyncio.create_task(
            _retry_ipn(payment_id, payment["orderId"], payment["amount"])
        )
    return {"status": "PAID", "ipnDelivered": delivered}


def abandon(payment_id: str) -> dict | None:
    payment = _payments.get(payment_id)
    if payment is None:
        return None
    payment["status"] = "ABANDONED"
    return {"status": "ABANDONED"}
