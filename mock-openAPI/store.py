import secrets
import time
import uuid
from dataclasses import dataclass
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from db import Base

# Docs: developer.v-app.vn/backend-api/open-api/scopes
# `auth` is silent login — user_id only, no consent screen.
#
# Note: @v-miniapp/apis@1.0.20 types only allow profile|phone|email.
# The SDK is behind the docs here; re-check once a real app is registered.
ALL_SCOPES = ("auth", "profile", "phone", "email")


class VAppUser(Base):
    """A V-App account.

    Persisted, because V-Market's users table is persisted too. If accounts
    lived in memory, a restart would leave V-Market holding rows that point
    at a vapp_user_id V-App no longer knows.
    """

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    date_of_birth: Mapped[str]
    gender: Mapped[str]
    phone_number: Mapped[str]
    email: Mapped[str]
    avatar_url: Mapped[str]


# Fixed IDs so tests can reach a known account after a restart. The names
# carry no role: V-App has no notion of buyer or seller, and V-Market
# decides that for itself.
SEED_USERS: tuple[dict, ...] = (
    {
        "user_id": "11111111-1111-4111-8111-111111111111",
        "name": "Nguyễn Thị An",
        "date_of_birth": "1995-04-12",
        "gender": "female",
        "phone_number": "+84901000001",
        "email": "an@example.com",
        "avatar_url": "https://placehold.co/128x128?text=A",
    },
    {
        # A fourth fixed account so V-Market can name one operator in its
        # own config. V-App still has no notion of roles — this is just
        # another person as far as the platform is concerned.
        "user_id": "44444444-4444-4444-8444-444444444444",
        "name": "Phạm Vận Hành",
        "date_of_birth": "1988-02-20",
        "gender": "male",
        "phone_number": "+84901000004",
        "email": "vanhanh@example.com",
        "avatar_url": "https://placehold.co/128x128?text=OPS",
    },
    {
        "user_id": "22222222-2222-4222-8222-222222222222",
        "name": "Trần Văn Bình",
        "date_of_birth": "1990-08-03",
        "gender": "male",
        "phone_number": "+84901000002",
        "email": "binh@example.com",
        "avatar_url": "https://placehold.co/128x128?text=B",
    },
    {
        "user_id": "33333333-3333-4333-8333-333333333333",
        "name": "Lê Thị Chi",
        "date_of_birth": "1992-12-21",
        "gender": "female",
        "phone_number": "+84901000003",
        "email": "chi@example.com",
        "avatar_url": "https://placehold.co/128x128?text=C",
    },
)


# Tickets stay in memory on purpose. An authCode lives 60 seconds and an
# access token an hour; losing them on restart is correct behaviour, and
# persisting them would only add expired rows to sweep up.
@dataclass
class _AuthCode:
    user_id: str
    scopes: list[str]
    expires_at: float
    used: bool = False


@dataclass
class _Token:
    user_id: str
    scopes: list[str]
    expires_at: float = 0.0


_auth_codes: dict[str, _AuthCode] = {}
_access_tokens: dict[str, _Token] = {}
_refresh_tokens: dict[str, _Token] = {}


def _opaque(prefix: str) -> str:
    # Tokens carry no payload. If user_id were encoded in here, someone
    # would decode it in the backend instead of calling userinfo, and
    # that code would break against the real API.
    return f"{prefix}_{secrets.token_hex(24)}"


def parse_scopes(raw: str | list[str] | None) -> list[str]:
    # Docs show both ['profile phone email'] and ['profile','phone','email'].
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    parts = [p for item in items for p in item.replace(",", " ").split()]
    return [p for p in parts if p in ALL_SCOPES]


async def seed_users(session: AsyncSession) -> None:
    """Insert the fixed accounts if they are not there yet."""
    for row in SEED_USERS:
        if await session.get(VAppUser, row["user_id"]) is None:
            session.add(VAppUser(**row))
    await session.commit()


async def find_user(session: AsyncSession, user_id: str) -> VAppUser | None:
    return await session.get(VAppUser, user_id)


async def all_users(session: AsyncSession) -> list[VAppUser]:
    return list(await session.scalars(select(VAppUser)))


async def create_user(
    session: AsyncSession,
    name: str,
    phone_number: str | None = None,
    email: str | None = None,
) -> VAppUser:
    """Register a V-App account.

    Registration belongs to V-App, not to V-Market. In production a person
    signs up with Vingroup once, and a MiniApp only ever receives an
    identity that already exists — which is why V-Market has no endpoint
    like this and never grows a password of its own.
    """
    suffix = uuid.uuid4().hex[:8]
    user = VAppUser(
        user_id=str(uuid.uuid4()),
        name=name,
        date_of_birth="2000-01-01",
        gender="unknown",
        phone_number=phone_number or f"+8490{int(suffix, 16) % 10**7:07d}",
        email=email or f"user-{suffix}@example.com",
        # quote() because a Vietnamese initial would break the URL otherwise.
        avatar_url=f"https://placehold.co/128x128?text={quote(name[:1].upper())}",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def issue_auth_code(user_id: str, scopes: list[str], ttl_seconds: int) -> str:
    code = f"ac_{uuid.uuid4()}"
    _auth_codes[code] = _AuthCode(
        user_id=user_id, scopes=scopes, expires_at=time.time() + ttl_seconds
    )
    return code


def consume_auth_code(code: str) -> tuple[str, list[str]] | str:
    """Single use. Returns (user_id, scopes), or a reason string on failure."""
    record = _auth_codes.get(code)
    if record is None:
        return "not_found"
    if record.used:
        return "already_used"
    if time.time() > record.expires_at:
        return "expired"

    record.used = True
    return record.user_id, record.scopes


def issue_tokens(
    user_id: str, scopes: list[str], ttl_seconds: int
) -> tuple[str, str]:
    access = _opaque("vat")
    refresh = _opaque("vrt")

    _access_tokens[access] = _Token(
        user_id=user_id, scopes=scopes, expires_at=time.time() + ttl_seconds
    )
    _refresh_tokens[refresh] = _Token(user_id=user_id, scopes=scopes)

    return access, refresh


def lookup_access_token(token: str) -> tuple[str, list[str]] | str:
    record = _access_tokens.get(token)
    if record is None:
        return "not_found"
    if time.time() > record.expires_at:
        del _access_tokens[token]
        return "expired"
    return record.user_id, record.scopes


def consume_refresh_token(token: str) -> _Token | None:
    record = _refresh_tokens.get(token)
    if record is None:
        return None
    # Rotate: a successful refresh returns a new refresh token too.
    del _refresh_tokens[token]
    return record


def project_user_info(user: VAppUser, scopes: list[str]) -> dict:
    """Return only the fields the token's scopes allow.

    The most important rule in this file. Returning every field
    regardless of scope would let the backend get used to always having
    phone_number, then break at checkout against the real API.
    """
    data: dict = {"user_id": user.user_id}

    if "profile" in scopes:
        data["name"] = user.name
        data["date_of_birth"] = user.date_of_birth
        data["gender"] = user.gender
        data["avatar_url"] = user.avatar_url
    if "phone" in scopes:
        data["phone_number"] = user.phone_number
    if "email" in scopes:
        data["email"] = user.email

    return data


def reset() -> None:
    """Drop the issued tickets. Accounts live in the database and stay."""
    _auth_codes.clear()
    _access_tokens.clear()
    _refresh_tokens.clear()
