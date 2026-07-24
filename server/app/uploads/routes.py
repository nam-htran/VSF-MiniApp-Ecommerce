"""Receiving product and shop images.

The MiniApp can't hotlink a third-party CDN — the whitelist only covers
domains the app owns — so images are uploaded here and served from the same
origin as the API.

Any logged-in user, not seller-only: opening a shop is where someone first
uploads a banner and logo, and they are still a BUYER at that moment — the
SELLER role is granted only once the shop is created (see shops/routes.py).
Requiring SELLER here would make the open-shop form impossible to complete,
the same chicken-and-egg that POST /shops already sidesteps. A valid V-App
session is still required, so this is not the open file host the guard was
guarding against.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile, status

from app.auth.deps import CurrentUser

router = APIRouter(tags=["Uploads"])

# server/uploads — created on import, served as static files from main.py.
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

_ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_BYTES = 5 * 1024 * 1024


@router.post("/uploads")
async def upload_image(
    request: Request, file: UploadFile, user: CurrentUser
) -> dict:
    extension = _ALLOWED.get(file.content_type or "")
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG or WebP images",
        )

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image too large (max 5MB)",
        )

    name = f"{uuid.uuid4().hex}{extension}"
    (UPLOAD_DIR / name).write_bytes(data)

    # An absolute URL built from however the client reached us, so the app
    # can put it straight into <img src> from its own origin — the dev port
    # now, a whitelisted host on a real device.
    base = str(request.base_url).rstrip("/")
    return {"url": f"{base}/uploads/{name}"}
