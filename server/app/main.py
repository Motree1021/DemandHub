from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import build_router
from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import get_engine
from app.standards.loader import load_all


def create_app(settings=None):
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        load_all()
        yield
        await get_engine().dispose()

    app = FastAPI(title="DemandHub", lifespan=lifespan, docs_url=None, redoc_url=None,
        openapi_url="/demandhub-api/openapi.json" if settings.app_env == "dev" else None)
    register_exception_handlers(app)
    app.include_router(build_router(settings))
    if settings.app_env == "dev":
        app.add_middleware(CORSMiddleware, allow_origins=[v.strip() for v in settings.cors_origins.split(",")],
            allow_credentials=False, allow_methods=["GET", "POST", "PUT"], allow_headers=["Authorization", "Content-Type"])
    return app


app = create_app()
