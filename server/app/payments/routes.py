"""Receiving payment notifications (IPN).

This is the merchant side of payment. The MiniApp never marks its own
order paid — it asks the gateway to charge, and the gateway tells the
server, server-to-server, once money has actually moved. That message is
what flips PENDING → PAID here.

Not behind the session guard: the caller is the gateway, not the buyer, so
there is no bearer token. Trust comes from the HMAC signature instead, and
from checking the amount against the order's own total.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.orders import store as orders
from app.payments.security import verify_hash

router = APIRouter(prefix="/payments", tags=["Payments"])

Session = Annotated[AsyncSession, Depends(get_session)]


class IpnRequest(BaseModel):
    paymentId: str
    orderId: str
    amount: int = Field(ge=0)
    status: str
    secureHash: str


@router.post("/ipn")
async def ipn(body: IpnRequest, session: Session) -> dict:
    if settings.payment_verify_hash and not verify_hash(
        settings.payment_ipn_secret,
        body.orderId,
        body.amount,
        body.status,
        body.secureHash,
    ):
        # 400, not 200: an unverifiable notification must not ack, so a
        # misconfigured gateway keeps retrying rather than silently losing
        # the payment.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature"
        )

    # Only a successful charge changes anything here; other states are
    # acknowledged so the gateway stops resending, but do nothing.
    if body.status != "PAID":
        return {"ok": True, "handled": False}

    order, result = await orders.mark_paid(
        session, body.orderId, Decimal(body.amount)
    )
    if result == "NOT_FOUND":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    if result == "AMOUNT_MISMATCH":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Amount mismatch"
        )

    # PAID or ALREADY_PAID: 200 either way — the retry-until-acked gateway
    # relies on a repeated notification being a success.
    assert order is not None
    return {"ok": True, "orderId": order.id, "status": order.status}
