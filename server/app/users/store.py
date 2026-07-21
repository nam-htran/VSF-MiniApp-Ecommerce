"""V-Market users.

`role` and `seller_id` are V-Market's data, not V-App's. V-App only
returns an identity — it has no notion of buyer or seller.

In memory for now; moves to a real DB on day 2 along with proper seeding.
"""

import uuid
from dataclasses import dataclass
from typing import Literal

UserRole = Literal["BUYER", "SELLER"]


@dataclass
class MarketUser:
    id: str
    vapp_user_id: str
    role: UserRole
    seller_id: str | None
    name: str | None
    phone_number: str | None


# Roles for the demo accounts. Deliberately a V-Market-side table, so the
# boundary with V-App stays visible.
_SEED_ROLES: dict[str, tuple[UserRole, str | None]] = {
    "11111111-1111-4111-8111-111111111111": ("BUYER", None),
    "22222222-2222-4222-8222-222222222222": ("SELLER", "seller-a"),
    "33333333-3333-4333-8333-333333333333": ("SELLER", "seller-b"),
}

_by_vapp_user_id: dict[str, MarketUser] = {}


def find_by_vapp_user_id(vapp_user_id: str) -> MarketUser | None:
    return _by_vapp_user_id.get(vapp_user_id)


def create_user(
    vapp_user_id: str, name: str | None, phone_number: str | None
) -> MarketUser:
    # New users default to BUYER; becoming a SELLER is a separate action
    # (creating a shop, day 3).
    role, seller_id = _SEED_ROLES.get(vapp_user_id, ("BUYER", None))

    user = MarketUser(
        id=str(uuid.uuid4()),
        vapp_user_id=vapp_user_id,
        role=role,
        seller_id=seller_id,
        name=name,
        phone_number=phone_number,
    )
    _by_vapp_user_id[vapp_user_id] = user
    return user


def reset() -> None:
    _by_vapp_user_id.clear()
