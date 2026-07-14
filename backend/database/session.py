from collections.abc import AsyncIterator

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config.config import settings, validate_settings


validate_settings()
db = settings.db

database_url = URL.create(
    drivername="postgresql+asyncpg",
    username=str(db.user),
    password=str(db.password),
    host=str(db.host),
    port=int(db.port),
    database=str(db.name),
)

async_engine = create_async_engine(
    database_url,
    echo=bool(db.get("echo", False)),
    pool_pre_ping=True,
)
async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(AsyncAttrs, DeclarativeBase):
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
