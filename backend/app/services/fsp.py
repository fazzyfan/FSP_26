"""Демонстрационный адаптер ФСП (FR-14, FR-15).

Интерфейс FSPProvider + демо-реализация. Демо-адаптер возвращает фиксированный
набор достижений для участника ФСП по номеру участника (fsp_member_id).
Реальная интеграция заменяет DemoFSPProvider без изменения вызывающего кода.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class FSPAchievement:
    code: str
    title: str
    description: str
    verified: bool


class FSPProvider(abc.ABC):
    """Контракт провайдера данных ФСП."""

    @abc.abstractmethod
    async def get_achievements(self, member_id: str | None) -> list[FSPAchievement]:
        """Достижения участника; пусто, если member_id не указан или не найден."""
        raise NotImplementedError


class DemoFSPProvider(FSPProvider):
    """Демо-адаптер: детерминированные достижения для проверки механик (FR-15)."""

    DEMO_ACHIEVEMENTS = [
        FSPAchievement(
            code="fsp_profile",
            title="Профиль участника ФСП",
            description="Участник подтверждён в системе ФСП.",
            verified=True,
        ),
        FSPAchievement(
            code="fsp_hackathon",
            title="Финалист хакатона ФСП",
            description="Проект команды вошёл в финал отраслевого хакатона.",
            verified=True,
        ),
        FSPAchievement(
            code="fsp_course",
            title="Курс ФСП пройден",
            description="Завершён профильный курс программы «Федеральные студенческие проекты».",
            verified=True,
        ),
    ]

    async def get_achievements(self, member_id: str | None) -> list[FSPAchievement]:
        if not member_id or not member_id.strip():
            return []
        # Номер участника в демо-режиме: любой непустой считается валидным
        return self.DEMO_ACHIEVEMENTS


def get_fsp_provider() -> FSPProvider:
    """Фабрика провайдера. Для MVP — демо-адаптер (FR-15)."""
    return DemoFSPProvider()