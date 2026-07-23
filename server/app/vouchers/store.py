"""Sale vouchers — real rows, real dates, one discount rule.

A voucher belongs to a shop, or to nobody (`shop_id` NULL) in which case it
is platform-wide. It is live only between `starts_at` and `ends_at`: once a
voucher expires it stops discounting and stops appearing in the promo strip,
without anyone editing it.

`discount_for` is the single implementation of the arithmetic. The price a
card advertises and the money an order actually charges both go through it,
so a displayed price can never disagree with what is billed — the one bug
that matters in a discount feature.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

DiscountType = Literal["PERCENT", "AMOUNT"]


class Voucher(Base):
    __tablename__ = "vouchers"
    __table_args__ = (
        CheckConstraint(
            "discount_type IN ('PERCENT', 'AMOUNT')",
            name="ck_vouchers_discount_type",
        ),
        CheckConstraint("discount_value > 0", name="ck_vouchers_value_positive"),
        # A percentage over 100 would pay the buyer to shop here.
        CheckConstraint(
            "discount_type <> 'PERCENT' OR discount_value <= 100",
            name="ck_vouchers_percent_range",
        ),
        CheckConstraint("min_order >= 0", name="ck_vouchers_min_order"),
        CheckConstraint("ends_at > starts_at", name="ck_vouchers_window"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    # Shown to the buyer and typed by nobody — the best one applies itself.
    code: Mapped[str] = mapped_column(unique=True, index=True)
    description: Mapped[str]
    # NULL = the whole marketplace; otherwise only this shop's items.
    shop_id: Mapped[str | None] = mapped_column(
        ForeignKey("shops.id"), index=True, default=None
    )
    # NULL = anything the shop sells; otherwise only items in this category.
    # A category key, matching products.category — the labels live on the
    # client, so renaming one never touches this column.
    category: Mapped[str | None] = mapped_column(default=None)
    discount_type: Mapped[str]
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Caps a percentage voucher. Meaningless for AMOUNT, left NULL there.
    max_discount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), default=None
    )
    min_order: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="ACTIVE")


def discount_for(voucher: Voucher, subtotal: Decimal) -> Decimal:
    """What this voucher takes off `subtotal`, or 0 if it doesn't apply.

    The only place the arithmetic lives. Never returns more than the
    subtotal — a 100k voucher on a 60k basket takes 60k, not 100k, and
    certainly never turns the line negative.
    """
    if subtotal < voucher.min_order:
        return Decimal("0")

    if voucher.discount_type == "AMOUNT":
        discount = voucher.discount_value
    else:
        discount = subtotal * voucher.discount_value / Decimal("100")
        if voucher.max_discount is not None:
            discount = min(discount, voucher.max_discount)

    # Money, so two decimals — and never more than what is owed.
    return min(discount, subtotal).quantize(Decimal("0.01"))


async def list_live(
    session: AsyncSession, shop_id: str | None = None, now: datetime | None = None
) -> list[Voucher]:
    """Vouchers usable right now: ACTIVE and inside their window.

    With `shop_id`, returns the ones that shop's basket could use — its own
    plus the platform-wide ones. Without it, everything currently live,
    which is what the promo strip shows.
    """
    moment = now or datetime.now(timezone.utc)
    conditions = [
        Voucher.status == "ACTIVE",
        Voucher.starts_at <= moment,
        Voucher.ends_at > moment,
    ]
    if shop_id is not None:
        conditions.append(
            or_(Voucher.shop_id.is_(None), Voucher.shop_id == shop_id)
        )

    rows = await session.scalars(
        select(Voucher).where(*conditions).order_by(Voucher.ends_at, Voucher.id)
    )
    return list(rows)


# A basket line as the voucher rules see it: what category it is in, and
# how much of it there is. Nothing else about a product matters here.
Line = tuple[str | None, Decimal]


def eligible_subtotal(voucher: Voucher, lines: list[Line]) -> Decimal:
    """How much of this basket the voucher is allowed to look at.

    A voucher with no category takes the whole lot; one with a category
    only ever sees lines in it. That is also what `min_order` is measured
    against — "giảm 50k cho đơn thời trang từ 300k" means 300k of clothes,
    not 300k of anything with one shirt in it.
    """
    if voucher.category is None:
        return sum((amount for _, amount in lines), Decimal("0"))
    return sum(
        (amount for category, amount in lines if category == voucher.category),
        Decimal("0"),
    )


def discount_on(voucher: Voucher, lines: list[Line]) -> Decimal:
    """What this voucher takes off a basket — eligibility, then arithmetic."""
    return discount_for(voucher, eligible_subtotal(voucher, lines))


def best_for(
    vouchers: list[Voucher], lines: list[Line]
) -> tuple[Voucher | None, Decimal]:
    """The voucher that takes the most off this basket, and how much.

    Ties break on the first listed, which `list_live` orders by soonest
    expiry — spend the one about to run out.
    """
    best: Voucher | None = None
    best_discount = Decimal("0")
    for voucher in vouchers:
        discount = discount_on(voucher, lines)
        if discount > best_discount:
            best, best_discount = voucher, discount
    return best, best_discount


def offers_for(vouchers: list[Voucher], lines: list[Line]) -> list[dict]:
    """Every voucher on offer for this basket, usable or not.

    Checkout shows the lot: the ones that bite, and the ones greyed out with
    the reason why — "chưa đủ 300.000₫", "không áp cho danh mục này". A
    voucher the buyer cannot see is a voucher they cannot work towards.
    """
    offers = []
    for voucher in vouchers:
        eligible = eligible_subtotal(voucher, lines)
        discount = discount_for(voucher, eligible)
        if eligible <= 0:
            reason = "Không áp dụng cho sản phẩm trong giỏ"
        elif eligible < voucher.min_order:
            reason = f"Cần thêm {voucher.min_order - eligible:.0f}₫"
        else:
            reason = None
        offers.append(
            {
                "voucher": voucher,
                "discount": discount,
                "applicable": reason is None and discount > 0,
                "reason": reason,
            }
        )
    return offers


async def create_voucher(
    session: AsyncSession,
    *,
    code: str,
    description: str,
    shop_id: str | None,
    category: str | None,
    discount_type: str,
    discount_value: Decimal,
    max_discount: Decimal | None,
    min_order: Decimal,
    starts_at: datetime,
    ends_at: datetime,
) -> Voucher:
    voucher = Voucher(
        id=str(uuid.uuid4()),
        code=code.upper(),
        description=description,
        shop_id=shop_id,
        category=category,
        discount_type=discount_type,
        discount_value=discount_value,
        max_discount=max_discount,
        min_order=min_order,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    session.add(voucher)
    await session.commit()
    await session.refresh(voucher)
    return voucher


async def list_for_shop(session: AsyncSession, shop_id: str) -> list[Voucher]:
    """Every voucher a shop owns, live or not — the seller's own list."""
    rows = await session.scalars(
        select(Voucher)
        .where(Voucher.shop_id == shop_id)
        .order_by(Voucher.ends_at.desc(), Voucher.id)
    )
    return list(rows)


async def find_by_id(session: AsyncSession, voucher_id: str) -> Voucher | None:
    return await session.get(Voucher, voucher_id)


async def set_status(
    session: AsyncSession, voucher: Voucher, status: str
) -> Voucher:
    voucher.status = status
    await session.commit()
    await session.refresh(voucher)
    return voucher
