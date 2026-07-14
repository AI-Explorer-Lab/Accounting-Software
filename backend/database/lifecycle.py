from sqlalchemy import text

from config.config import settings
from constant.enums import Environment
from database.session import Base, async_engine


async def init_database() -> None:
    """Verify that PostgreSQL accepts connections before serving requests."""
    async with async_engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def close_database() -> None:
    await async_engine.dispose()


async def create_tables() -> None:
    environment_name = str(settings.environment.name).lower()
    allowed = {Environment.DEVELOPMENT.value, Environment.TEST.value}
    if environment_name not in allowed or not settings.environment.get(
        "create_tables", False
    ):
        return

    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
