"""所有集成测试只使用 demandhub_test；鉴权与业务使用同一个受控 factory。"""
import os

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command

os.environ["APP_ENV"] = "test"
os.environ["DEMANDHUB_DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "mysql://root:local-test-only-password@127.0.0.1:3308/demandhub_test")
os.environ["JWT_SECRET"] = "unit-test-only-secret-at-least-32-characters"
os.environ["AUTH_DEV_LOGIN"] = "true"
os.environ["AUTH_TEST_LOGIN"] = "true"
os.environ["ADMIN_WECOM_USERIDS"] = "mvp-admin"
os.environ["CHANNEL_LS_BASE_URL"] = "http://127.0.0.1:8199"
os.environ["CHANNEL_LS_APP_KEY"] = "demandhub-dev"
os.environ["CHANNEL_LS_APP_SECRET"] = "local-mock-only-secret"

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database():
    get_settings.cache_clear()
    settings = get_settings()
    if settings.database_url.database != "demandhub_test":
        raise RuntimeError("测试只允许 demandhub_test 数据库")
    command.upgrade(Config("alembic.ini"), "head")


@pytest_asyncio.fixture
async def session_factory(monkeypatch):
    from app.core import deps
    from app.db import session
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(session, "get_session_factory", lambda: factory)
    monkeypatch.setattr(deps, "get_session_factory", lambda: factory)
    async def clean():
        async with factory() as db:
            async with db.begin():
                for table in reversed(Base.metadata.sorted_tables):
                    await db.execute(delete(table))
    await clean()
    yield factory
    await clean()
    await engine.dispose()


@pytest_asyncio.fixture
async def db(session_factory):
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def client(session_factory):
    from app.main import create_app
    app = create_app(get_settings())
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def user(session_factory):
    from app.db.models import User
    async with session_factory() as db:
        async with db.begin():
            user = User(name="测试用户", wecom_userid="test-user", channel="CHUANGJIN_LS")
            db.add(user)
            await db.flush()
        return user


@pytest_asyncio.fixture
async def auth_headers(client):
    response = await client.post("/demandhub-api/auth/dev-login", json={"name": "测试用户", "wecomUserid": "test-user"})
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}
