"""Generic PostgreSQL mapper helpers to be specialized by future entities."""

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import Base


EntityT = TypeVar("EntityT", bound=Base)


async def create(session: AsyncSession, entity: EntityT) -> EntityT:
    session.add(entity)
    await session.flush()
    await session.refresh(entity)
    return entity


async def get(
    session: AsyncSession, model: type[EntityT], entity_id: Any
) -> EntityT | None:
    return await session.get(model, entity_id)


async def list(
    session: AsyncSession,
    model: type[EntityT],
    *,
    offset: int = 0,
    limit: int = 100,
) -> Sequence[EntityT]:
    result = await session.scalars(select(model).offset(offset).limit(limit))
    return result.all()


async def update(
    session: AsyncSession,
    entity: EntityT,
    changes: Mapping[str, Any],
) -> EntityT:
    for field, value in changes.items():
        if not hasattr(entity, field):
            raise ValueError(f"Unknown entity field: {field}")
        setattr(entity, field, value)
    await session.flush()
    await session.refresh(entity)
    return entity


async def delete(session: AsyncSession, entity: EntityT) -> None:
    await session.delete(entity)
    await session.flush()
