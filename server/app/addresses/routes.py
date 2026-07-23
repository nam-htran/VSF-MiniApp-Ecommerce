"""The buyer's address book. Every route is scoped to the caller — an id
from the client is only ever used after confirming the caller owns it, so
one user can never read or change another's addresses (same rule as orders).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses import store as addresses
from app.addresses.store import Address
from app.auth.deps import CurrentUser
from app.db import get_session

router = APIRouter(prefix="/addresses", tags=["Addresses"])

Session = Annotated[AsyncSession, Depends(get_session)]


class AddressRequest(BaseModel):
    recipientName: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=8, max_length=20)
    addressLine: str = Field(min_length=5, max_length=500)
    isDefault: bool = False


def _serialise(address: Address) -> dict:
    return {
        "id": address.id,
        "recipientName": address.recipient_name,
        "phone": address.phone,
        "addressLine": address.address_line,
        "isDefault": address.is_default,
        "createdAt": address.created_at.isoformat(),
    }


@router.get("")
async def my_addresses(user: CurrentUser, session: Session) -> list[dict]:
    rows = await addresses.list_for_user(session, user.id)
    return [_serialise(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_address(
    body: AddressRequest, user: CurrentUser, session: Session
) -> dict:
    address = await addresses.create(
        session,
        user_id=user.id,
        recipient_name=body.recipientName.strip(),
        phone=body.phone.strip(),
        address_line=body.addressLine.strip(),
        make_default=body.isDefault,
    )
    return _serialise(address)


@router.post("/{address_id}/default")
async def make_default(
    address_id: str, user: CurrentUser, session: Session
) -> dict:
    address = await addresses.find_owned(session, user.id, address_id)
    if address is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Address not found"
        )
    updated = await addresses.set_default(session, user.id, address)
    return _serialise(updated)


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_address(
    address_id: str, user: CurrentUser, session: Session
) -> None:
    address = await addresses.find_owned(session, user.id, address_id)
    if address is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Address not found"
        )
    await addresses.delete(session, user.id, address)
