from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings


@lru_cache
def get_engine():
    return create_async_engine(get_settings().database_url, pool_pre_ping=True, pool_recycle=1800)


@lru_cache
def get_session_factory():
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db():
    async with get_session_factory()() as db:
        yield db
