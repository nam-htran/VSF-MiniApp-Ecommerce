from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth.routes import router as auth_router
from app.config import settings
from app.db import create_tables, engine
from app.json_response import SafeJSONResponse
from app.addresses.routes import router as addresses_router
from app.geo.routes import router as geo_router
from app.orders.routes import router as orders_router
from app.payments.routes import router as payments_router
from app.reviews.routes import router as reviews_router
from app.uploads.routes import UPLOAD_DIR, router as uploads_router
from app.products.routes import router as products_router
from app.shops.routes import router as shops_router
from app.vouchers.routes import router as vouchers_router

# Imported so SQLAlchemy knows about the models before create_tables() runs.
from app.addresses import store as _addresses  # noqa: F401
from app.orders import store as _orders  # noqa: F401
from app.reviews import store as _reviews  # noqa: F401
from app.products import store as _products  # noqa: F401
from app.shops import store as _shops  # noqa: F401
from app.users import store as _users  # noqa: F401
from app.vouchers import store as _vouchers  # noqa: F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_tables()
    yield
    # Hand the Postgres connections back instead of having them cut off.
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="V-Market Backend",
        version="0.1.0",
        lifespan=lifespan,
        # Sellers author product text, so no response body may be readable
        # as markup — see app/json_response.py.
        default_response_class=SafeJSONResponse,
    )

    # For the Simulator only. Its bridge refuses plain-http URLs, so in dev
    # the MiniApp falls back to the browser's own fetch — a cross-origin
    # call from the dev server's port to 4000, which needs CORS. Scoped to
    # local origins: a real device talks HTTPS through the platform bridge
    # and never sends a localhost Origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["System"])
    async def healthz() -> dict:
        return {"status": "ok", "vappBaseUrl": settings.vapp_base_url}

    app.include_router(auth_router)
    app.include_router(shops_router)
    app.include_router(products_router)
    app.include_router(orders_router)
    app.include_router(geo_router)
    app.include_router(addresses_router)
    app.include_router(payments_router)
    app.include_router(reviews_router)
    app.include_router(vouchers_router)
    app.include_router(uploads_router)
    # Serve uploaded product images from the same origin as the API.
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
    return app


app = create_app()
