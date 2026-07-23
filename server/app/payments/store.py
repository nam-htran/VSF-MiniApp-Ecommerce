"""Money that arrived but could not be applied.

A payment notification the merchant cannot honour — for an order already
cancelled, for an amount that doesn't match, for an order that vanished —
is not a validation error to log and forget. The buyer's money has moved.
Answering the gateway with an error is right, but it only stops the
merchant lying; it does nothing for the person out of pocket.

So every one of them becomes a row here, with enough to refund from: the
gateway's own payment id, the amount, and why it could not be applied.
Refunding is a manual step for now — a demo has no treasury — but the debt
is recorded rather than lost, which is the part that must not wait.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PaymentException(Base):
    __tablename__ = "payment_exceptions"

    id: Mapped[str] = mapped_column(primary_key=True)
    # The gateway's id, not ours: it is what a refund is issued against, and
    # it is the one identifier that still means something when our own order
    # has been cancelled.
    gateway_payment_id: Mapped[str] = mapped_column(index=True)
    # Not a foreign key: an IPN can name an order that never existed, and a
    # constraint would reject exactly the row worth keeping.
    order_id: Mapped[str | None] = mapped_column(default=None, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str]
    # OPEN until someone refunds or reconciles it.
    status: Mapped[str] = mapped_column(default="OPEN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


async def record(
    session: AsyncSession,
    *,
    gateway_payment_id: str,
    order_id: str | None,
    amount: Decimal,
    reason: str,
) -> PaymentException:
    """Log money we could not apply. Idempotent per gateway payment, since
    the gateway retries until it is acked and must not create a queue of
    identical debts."""
    existing = await session.scalar(
        select(PaymentException).where(
            PaymentException.gateway_payment_id == gateway_payment_id,
            PaymentException.status == "OPEN",
        )
    )
    if existing is not None:
        return existing

    entry = PaymentException(
        id=str(uuid.uuid4()),
        gateway_payment_id=gateway_payment_id,
        order_id=order_id,
        amount=amount,
        reason=reason,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def list_open(session: AsyncSession) -> list[PaymentException]:
    rows = await session.scalars(
        select(PaymentException)
        .where(PaymentException.status == "OPEN")
        .order_by(PaymentException.created_at)
    )
    return list(rows)
