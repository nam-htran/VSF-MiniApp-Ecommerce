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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.auth.deps import CurrentAdmin, CurrentUser
from app.db import get_session
from app.orders import store as orders
from app.payments import gateway
from app.payments import store as exceptions
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
        # Money against an order we have never heard of. Worth keeping more,
        # not less: there is nobody else holding this record.
        await exceptions.record(
            session,
            gateway_payment_id=body.paymentId,
            order_id=body.orderId,
            amount=Decimal(body.amount),
            reason="Không tìm thấy đơn hàng",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    if result == "AMOUNT_MISMATCH":
        await exceptions.record(
            session,
            gateway_payment_id=body.paymentId,
            order_id=body.orderId,
            amount=Decimal(body.amount),
            reason="Số tiền không khớp đơn hàng",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Amount mismatch"
        )
    if result == "NOT_PAYABLE":
        # The order is no longer PENDING and was not already paid — it was
        # cancelled, most likely because its stock hold lapsed while the
        # buyer was still at the gateway. Acking this with 200 would tell
        # the gateway everything is fine while the buyer's money has moved
        # against an order that no longer exists and stock that has already
        # gone back on sale. Refuse loudly so it is reconciled, not lost.
        assert order is not None
        await exceptions.record(
            session,
            gateway_payment_id=body.paymentId,
            order_id=body.orderId,
            amount=Decimal(body.amount),
            reason=f"Đơn ở trạng thái {order.status}, cần hoàn tiền",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is {order.status}, cannot be paid",
        )

    # PAID or ALREADY_PAID: 200 either way — the retry-until-acked gateway
    # relies on a repeated notification being a success.
    assert order is not None
    return {"ok": True, "orderId": order.id, "status": order.status}


class OpenSessionRequest(BaseModel):
    orderId: str


@router.post("/session")
async def open_payment_session(
    body: OpenSessionRequest, user: CurrentUser, session: Session
) -> dict:
    """Open a payment through the server rather than from the client.

    The MiniApp used to call the gateway directly, which left this server
    unable to tell "buyer abandoned the basket" from "buyer is entering an
    OTP" — and the stock-hold sweep would cancel the second, taking the
    money while giving the goods to someone else. Going through here
    records the session on the order, so the hold is extended instead.
    """
    order = await orders.find_by_id(session, body.orderId)
    if order is None or order.buyer_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    if order.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Đơn ở trạng thái {order.status}, không thể thanh toán",
        )

    opened = await gateway.open_session(order.id, int(order.total))
    await orders.attach_payment(session, order.id, user.id, opened["paymentId"])
    return {"paymentId": opened["paymentId"], "amount": float(order.total)}


@router.get("/exceptions")
async def list_exceptions(_: CurrentAdmin, session: Session) -> dict:
    """Money received that could not be applied, still awaiting a refund.

    Operator-only: it lists gateway payment ids and amounts across every
    shop, which is what a refund is issued against and therefore not
    something to leave open to the internet.
    """
    rows = await exceptions.list_open(session)
    return {
        "items": [
            {
                "id": row.id,
                "gatewayPaymentId": row.gateway_payment_id,
                "orderId": row.order_id,
                "amount": float(row.amount),
                "reason": row.reason,
                "status": row.status,
                "createdAt": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.post("/reconcile")
async def reconcile(
    session: Session,
    older_than_seconds: Annotated[int, Query(ge=0)] = 60,
) -> dict:
    """Ask the gateway about orders we never got a webhook for.

    Public on purpose: it changes nothing a correct webhook wouldn't, and
    it needs to be callable by a cron job or a health check that holds no
    session. Everything it applies goes through the same amount check the
    webhook does.
    """
    return await orders.reconcile_pending(session, older_than_seconds)


@router.post("/exceptions/{exception_id}/resolve")
async def resolve_exception(
    exception_id: str, _: CurrentAdmin, session: Session
) -> dict:
    """Mark a debt settled, once the refund has actually been issued.

    Nothing here moves money — this project has no treasury and the mock
    gateway has no refund call. It records that a human did, which is what
    stops the same payment being refunded twice.
    """
    entry = await exceptions.resolve(session, exception_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
        )
    return {"id": entry.id, "status": entry.status}
