"""Receiving product images.

The MiniApp can't hotlink a third-party CDN — the whitelist only covers
domains the app owns — so seller images are uploaded here and served from
the same origin as the API. Seller-only: an upload endpoint open to anyone
is a free file host.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile, status

from app.auth.deps import CurrentSeller

router = APIRouter(tags=["Uploads"])

# server/uploads — created on import, served as static files from main.py.
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

_ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_BYTES = 5 * 1024 * 1024


@router.post("/uploads")
async def upload_image(
    request: Request, file: UploadFile, seller: CurrentSeller
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
