import secrets
import time
import uuid
from dataclasses import dataclass

# Docs: developer.v-app.vn/backend-api/open-api/scopes
# `auth` is silent login — user_id only, no consent screen.
#
# Note: @v-miniapp/apis@1.0.20 types only allow profile|phone|email.
# The SDK is behind the docs here; re-check once a real app is registered.
ALL_SCOPES = ("auth", "profile", "phone", "email")


@dataclass(frozen=True)
class VAppUser:
    user_id: str
    name: str
    date_of_birth: str
    gender: str
    phone_number: str
    email: str
    avatar_url: str


# Fixed IDs so V-Market's seed data still matches after a restart.
# V-App has no notion of buyer/seller — that is V-Market's data.
SEED_USERS: tuple[VAppUser, ...] = (
    VAppUser(
        user_id="11111111-1111-4111-8111-111111111111",
        name="Nguyễn Thị Mua",
        date_of_birth="1995-04-12",
        gender="female",
        phone_number="+84901000001",
        email="buyer@example.com",
        avatar_url="https://placehold.co/128x128?text=Buyer",
    ),
    VAppUser(
        user_id="22222222-2222-4222-8222-222222222222",
        name="Trần Văn Bán A",
        date_of_birth="1990-08-03",
        gender="male",
        phone_number="+84901000002",
        email="seller-a@example.com",
        avatar_url="https://placehold.co/128x128?text=A",
    ),
    VAppUser(
        user_id="33333333-3333-4333-8333-333333333333",
        name="Lê Thị Bán B",
        date_of_birth="1992-12-21",
        gender="female",
        phone_number="+84901000003",
        email="seller-b@example.com",
        avatar_url="https://placehold.co/128x128?text=B",
    ),
)


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


def find_user(user_id: str) -> VAppUser | None:
    return next((u for u in SEED_USERS if u.user_id == user_id), None)


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
    _auth_codes.clear()
    _access_tokens.clear()
    _refresh_tokens.clear()
