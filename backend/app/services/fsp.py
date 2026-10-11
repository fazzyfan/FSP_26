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
    """Демо-адаптер: детерминированные достижения для проверки механик (FR-15).

    Известные тестовые ID участников получают свои достижения; неизвестный ID
    не подтверждается и не даёт бонуса в подборе (UPD 4, п.5). Реальная
    интеграция заменяет этот класс без изменения вызывающего кода.
    """

    # Известные тестовые ID: каждый получает свой набор достижений
    KNOWN_MEMBER_IDS: dict[str, list[str]] = {
        "FSP-2026-0001": ["fsp_profile", "fsp_hackathon", "fsp_course"],
        "FSP-2026-0002": ["fsp_profile", "fsp_course"],
        "FSP-2026-0003": ["fsp_profile"],
    }

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
        codes = self.KNOWN_MEMBER_IDS.get(member_id.strip())
        if codes is None:
            return []  # неизвестный ID: без подтверждения и бонуса
        by_code = {a.code: a for a in self.DEMO_ACHIEVEMENTS}
        return [by_code[c] for c in codes if c in by_code]


def get_fsp_provider() -> FSPProvider:
    """Фабрика провайдера. Для MVP — демо-адаптер (FR-15)."""
    return DemoFSPProvider()