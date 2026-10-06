"""Бизнес-логика тестирования и подтверждённой категории (FR-08..FR-13, D-02..D-06).

Правила (значения из конфигурации):
- порог Junior >= 50%, Middle >= 70%;
- повтор после неуспеха через 24 ч, после успеха через 90 дней;
- одна активная категория; понижение грейда результатом не выполняется.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.config import Settings
from app.models.assessment import (
    ConfirmedCategory,
    TestAttempt,
    TestAttemptAnswer,
    TestAttemptStatus,
    TestQuestion,
)
from app.models.reference import Grade


async def questions_for_specialization(db: AsyncSession, specialization_id: uuid.UUID) -> list[TestQuestion]:
    return list(
        (
            await db.scalars(
                select(TestQuestion)
                .where(TestQuestion.specialization_id == specialization_id, TestQuestion.is_active.is_(True))
                .order_by(TestQuestion.sort_order, TestQuestion.text)
            )
        ).all()
    )


def next_attempt_at(last: TestAttempt | None, settings: Settings) -> datetime | None:
    """Дата следующей допустимой попытки: None — можно проходить сейчас."""
    if last is None or last.submitted_at is None:
        return None
    if last.result_grade_id is None:
        return last.submitted_at + timedelta(hours=settings.test_retry_failed_hours)
    return last.submitted_at + timedelta(days=settings.test_retry_success_days)


async def last_completed_attempt(db: AsyncSession, candidate_id: uuid.UUID) -> TestAttempt | None:
    return await db.scalar(
        select(TestAttempt)
        .where(TestAttempt.candidate_id == candidate_id, TestAttempt.status == TestAttemptStatus.COMPLETED)
        .order_by(TestAttempt.submitted_at.desc())
        .limit(1)
    )


async def active_category(db: AsyncSession, candidate_id: uuid.UUID) -> ConfirmedCategory | None:
    return await db.scalar(
        select(ConfirmedCategory).where(
            ConfirmedCategory.candidate_id == candidate_id, ConfirmedCategory.is_active.is_(True)
        )
    )


def grade_level_for_score(score_percent: int, settings: Settings) -> int | None:
    """Уровень грейда по результату (D-01: Junior=1, Middle=2)."""
    if score_percent >= settings.test_pass_middle_percent:
        return 2
    if score_percent >= settings.test_pass_junior_percent:
        return 1
    return None


async def grade_by_level(db: AsyncSession, level: int) -> Grade | None:
    return await db.scalar(select(Grade).where(Grade.level == level))


def compute_next_attempt_at(attempt: TestAttempt, settings: Settings) -> datetime:
    """Кудаун после конкретной попытки: 24 ч при неуспехе, 90 дней при успехе."""
    if attempt.result_grade_id is None:
        return attempt.submitted_at + timedelta(hours=settings.test_retry_failed_hours)
    return attempt.submitted_at + timedelta(days=settings.test_retry_success_days)


async def apply_result_category(
    db: AsyncSession,
    candidate_id: uuid.UUID,
    specialization_id: uuid.UUID,
    grade: Grade,
    attempt: TestAttempt,
) -> ConfirmedCategory | None:
    """Обновление активной категории: апгрейд или смена специализации; понижение игнорируется."""
    active = await active_category(db, candidate_id)
    if active is not None and active.specialization_id == specialization_id and active.grade.level >= grade.level:
        return active  # равный или более низкий грейд — текущую категорию не меняем
    if active is not None:
        active.is_active = False
    category = ConfirmedCategory(
        candidate_id=candidate_id,
        specialization_id=specialization_id,
        grade_id=grade.id,
        source_attempt_id=attempt.id,
        is_active=True,
    )
    db.add(category)
    return category


def build_attempt_result(
    attempt: TestAttempt,
    settings: Settings,
    next_at: datetime,
    message: str,
) -> dict:
    return {
        "attempt_id": attempt.id,
        "specialization_id": attempt.specialization_id,
        "specialization_name": attempt.specialization.name if attempt.specialization else "",
        "status": attempt.status.value,
        "correct_count": attempt.correct_count,
        "total_count": attempt.total_count,
        "score_percent": attempt.score_percent or 0,
        "passed": attempt.result_grade_id is not None,
        "grade_code": attempt.result_grade.code if attempt.result_grade else None,
        "grade_name": attempt.result_grade.name if attempt.result_grade else None,
        "next_attempt_at": next_at.isoformat(),
        "message": message,
    }