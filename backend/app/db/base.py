"""Слой доступа к БД: движок, фабрика сессий, метаданные."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# echo=False: SQL-лог слишком шумный для консоли Windows (cp1252); диагностика идёт через структурированный лог
engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс моделей."""


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость сессии БД."""
    async with async_session_factory() as session:
        yield session