from fastapi import FastAPI

from app.auth.routes import router as auth_router
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="V-Market Backend", version="0.1.0")

    @app.get("/healthz", tags=["System"])
    async def healthz() -> dict:
        return {"status": "ok", "vappBaseUrl": settings.vapp_base_url}

    app.include_router(auth_router)
    return app


app = create_app()
