from fastapi import APIRouter


def build_router(settings):
    from app.api import admin, agent, auth, demand, health, standards
    router = APIRouter(prefix=settings.api_root_path)
    for module in (health, auth, standards, demand, admin, agent):
        router.include_router(module.router)
    if settings.auth_dev_login:
        router.include_router(auth.dev_router)
    return router
