from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
        # P2：启动时从配置表加载状态机规则（热重载走 POST /admin/state-machines/reload）
        from app.core.statemachine import engine as statemachine_engine
        from app.db.session import get_session_factory
        async with get_session_factory()() as db:
            await statemachine_engine.load_from_db(db)
        # P4：SLA 超时扫描后台任务（asyncio 先例，无外部调度器）
        sla_task = sla_stop = None
        if settings.sla_scan_enabled:
            from app.services import sla_service
            sla_task, sla_stop = sla_service.start_scanner(settings.sla_scan_interval_seconds)
        # P4：demand_stat_daily 当日快照定时刷新（看板实时 SQL 不读快照，仅落档）
        stat_task = stat_stop = None
        if settings.stat_refresh_enabled:
            from app.services import stat_service
            stat_task, stat_stop = stat_service.start_refresher(settings.stat_refresh_interval_seconds)
        yield
        if sla_task is not None:
            sla_stop.set()
            await sla_task
        if stat_task is not None:
            stat_stop.set()
            await stat_task
        await get_engine().dispose()

    app = FastAPI(title="DemandHub", lifespan=lifespan, docs_url=None, redoc_url=None,
        openapi_url="/demandhub-api/openapi.json" if settings.app_env == "dev" else None)
    register_exception_handlers(app)
    app.include_router(build_router(settings))
    # 管理后台静态托管（P1）：构建产物随服务同容器发布，前端用 hash 路由无需 rewrite。
    # 挂载路径须带 api_root_path 前缀：网关不剥前缀转发，API 路由均以 /demandhub-api 注册，
    # 静态挂载挂 /admin 会因路径不匹配 404（本地直连 :8000/admin/ 能通掩盖了该问题）
    admin_dist = Path(__file__).resolve().parents[2] / "frontend" / "admin" / "dist"
    if admin_dist.is_dir():
        app.mount(f"{settings.api_root_path}/admin", StaticFiles(directory=admin_dist, html=True), name="admin")
    if settings.app_env == "dev":
        app.add_middleware(CORSMiddleware, allow_origins=[v.strip() for v in settings.cors_origins.split(",")],
            allow_credentials=False, allow_methods=["GET", "POST", "PUT"], allow_headers=["Authorization", "Content-Type"])
    return app


app = create_app()
