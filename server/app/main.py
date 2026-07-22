from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth.routes import router as auth_router
from app.config import settings
from app.db import create_tables, engine
from app.products.routes import router as products_router
from app.shops.routes import router as shops_router

# Imported so SQLAlchemy knows about the models before create_tables() runs.
from app.products import store as _products  # noqa: F401
from app.shops import store as _shops  # noqa: F401
from app.users import store as _users  # noqa: F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_tables()
    yield
    # Hand the Postgres connections back instead of having them cut off.
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="V-Market Backend", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz", tags=["System"])
    async def healthz() -> dict:
        return {"status": "ok", "vappBaseUrl": settings.vapp_base_url}

    app.include_router(auth_router)
    app.include_router(shops_router)
    app.include_router(products_router)
    return app


app = create_app()
