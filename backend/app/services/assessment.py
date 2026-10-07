"""Бизнес-логика тестирования и подтверждённой категории (FR-08..FR-13).

Правила MVP:
- 4 категории: специализация × грейд (Junior/Middle), выбор до старта теста;
- попытка создаётся на старте, живёт 20 минут (серверный таймер);
- ответы сохраняются по мере выбора и восстанавливаются после перезагрузки;
- одна активная попытка; submit закрывает попытку, повторная отправка и
  перезапись старых данных отклоняются;
- категория подтверждается при сумме >= 70% и >= 50% в каждом из 3 блоков;
- пересдача той же категории — через 24 ч, смена подтверждённой — через 90 дней.
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

BLOCKS = (1, 2, 3)


async def questions_for_category(
    db: AsyncSession, specialization_id: uuid.UUID, grade_level: int
) -> list[TestQuestion]:
    """Вопросы теста выбранной категории: 6 заданий (3 блока по 2)."""
    return list(
        (
            await db.scalars(
                select(TestQuestion)
                .where(
                    TestQuestion.specialization_id == specialization_id,
                    TestQuestion.grade_level == grade_level,
                    TestQuestion.is_active.is_(True),
                )
                .order_by(TestQuestion.block, TestQuestion.sort_order)
            )
        ).all()
    )


def next_attempt_at(last: TestAttempt | None, settings: Settings) -> datetime | None:
    """Пересдача той же категории: через 24 часа после завершённой попытки.

    Просроченные попытки (expired) не создают кулдауна — кандидат может
    начать новую попытку сразу после истечения таймера.
    """
    if (
        last is None
        or last.status != TestAttemptStatus.COMPLETED
        or last.submitted_at is None
    ):
        return None
    return last.submitted_at + timedelta(hours=settings.test_retry_failed_hours)


async def last_attempt_for_category(
    db: AsyncSession, candidate_id: uuid.UUID, specialization_id: uuid.UUID, grade_level: int
) -> TestAttempt | None:
    """Последняя завершённая попытка по категории (для правила 24 часов)."""
    return await db.scalar(
        select(TestAttempt)
        .where(
            TestAttempt.candidate_id == candidate_id,
            TestAttempt.specialization_id == specialization_id,
            TestAttempt.grade_level == grade_level,
            TestAttempt.status == TestAttemptStatus.COMPLETED,
        )
        .order_by(TestAttempt.submitted_at.desc())
        .limit(1)
    )


async def active_in_progress_attempt(db: AsyncSession, candidate_id: uuid.UUID) -> TestAttempt | None:
    return await db.scalar(
        select(TestAttempt).where(
            TestAttempt.candidate_id == candidate_id,
            TestAttempt.status == TestAttemptStatus.IN_PROGRESS,
        )
    )


async def active_category(db: AsyncSession, candidate_id: uuid.UUID) -> ConfirmedCategory | None:
    return await db.scalar(
        select(ConfirmedCategory).where(
            ConfirmedCategory.candidate_id == candidate_id, ConfirmedCategory.is_active.is_(True)
        )
    )


async def grade_by_level(db: AsyncSession, level: int) -> Grade | None:
    return await db.scalar(select(Grade).where(Grade.level == level))


def remaining_seconds(attempt: TestAttempt, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    return max(0, int((attempt.expires_at - now).total_seconds()))


def mark_expired(attempt: TestAttempt, now: datetime | None = None) -> bool:
    """Помечает просроченную попытку EXPIRED; возвращает True, если только что истекла."""
    now = now or datetime.now(UTC)
    if attempt.status == TestAttemptStatus.IN_PROGRESS and now >= attempt.expires_at:
        attempt.status = TestAttemptStatus.EXPIRED
        attempt.submitted_at = attempt.expires_at
        return True
    return False


async def ensure_can_start(
    db: AsyncSession,
    candidate_id: uuid.UUID,
    specialization_id: uuid.UUID,
    grade_level: int,
    settings: Settings,
) -> None:
    """Допуск к старту теста выбранной категории (кулдауны FR-13)."""
    now = datetime.now(UTC)

    # Одна активная попытка; просроченная таймером попытка освобождает слот
    active = await active_in_progress_attempt(db, candidate_id)
    if active is not None:
        if mark_expired(active):
            await db.commit()
        elif active.specialization_id == specialization_id and active.grade_level == grade_level:
            return  # продолжение существующей попытки
        else:
            raise errors.Problem(
                409, errors.INVALID_STATE, errors.E12_STATE, "Уже есть активная попытка теста",
                detail="Завершите или дождитесь истечения текущей попытки перед началом новой.",
                recovery="correct_input",
            )

    # Пересдача той же категории: через 24 часа
    last = await last_attempt_for_category(db, candidate_id, specialization_id, grade_level)
    if last is not None and last.submitted_at is not None:
        nxt = next_attempt_at(last, settings)
        if nxt is not None and now < nxt:
            raise errors.Problem(
                409, errors.INVALID_STATE, errors.E13_TIME, "Повтор теста пока недоступен",
                detail=f"Пересдача этой категории доступна с {nxt.isoformat()}.",
                recovery="wait", extra={"next_allowed_at": nxt.isoformat()},
            )

    # Смена подтверждённой категории: через 90 дней после назначения/смены
    category = await active_category(db, candidate_id)
    if category is not None and (category.specialization_id != specialization_id or category.grade.level != grade_level):
        nxt = category.confirmed_at + timedelta(days=settings.test_change_category_days)
        if now < nxt:
            raise errors.Problem(
                409, errors.INVALID_STATE, errors.E13_TIME, "Смена категории пока недоступна",
                detail=f"Подтверждённую категорию можно сменить с {nxt.isoformat()}.",
                recovery="wait", extra={"next_allowed_at": nxt.isoformat()},
            )


async def start_attempt(
    db: AsyncSession,
    candidate_id: uuid.UUID,
    specialization_id: uuid.UUID,
    grade_level: int,
    settings: Settings,
) -> TestAttempt:
    """Создаёт (или продолжает) активную попытку теста с серверным таймером."""
    await ensure_can_start(db, candidate_id, specialization_id, grade_level, settings)

    existing = await active_in_progress_attempt(db, candidate_id)
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    attempt = TestAttempt(
        candidate_id=candidate_id,
        specialization_id=specialization_id,
        grade_level=grade_level,
        status=TestAttemptStatus.IN_PROGRESS,
        started_at=now,
        expires_at=now + timedelta(minutes=settings.test_timeout_minutes),
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def attempt_answers_map(db: AsyncSession, attempt: TestAttempt) -> dict[uuid.UUID, TestAttemptAnswer]:
    return {a.question_id: a for a in attempt.answers}


async def save_answers(
    db: AsyncSession,
    attempt: TestAttempt,
    answers: list[tuple[uuid.UUID, uuid.UUID]],
    valid_question_ids: set[uuid.UUID],
) -> None:
    """Upsert ответов активной попытки. Завершённые/просроченные попытки закрыты."""
    if attempt.status != TestAttemptStatus.IN_PROGRESS:
        raise errors.Problem(
            409, errors.INVALID_STATE, errors.E12_STATE, "Попытка уже завершена",
            detail="Ответы можно сохранять только в активной попытке.",
            recovery="none",
        )
    if mark_expired(attempt):
        await db.commit()
        raise errors.Problem(
            409, errors.INVALID_STATE, errors.E13_TIME, "Время попытки истекло",
            detail="Серверный таймер попытки истёк. Начните новую попытку.",
            recovery="retry",
        )

    existing = await attempt_answers_map(db, attempt)
    for qid, opt_id in answers:
        if qid not in valid_question_ids:
            raise errors.Problem(
                422, errors.VALIDATION_FAILED, errors.E04_REFERENCE, "Неизвестный вопрос",
                errors=[{"field": "answers", "code": "REFERENCE_INVALID", "error_class": "E04",
                         "message": "Вопрос не входит в тест этой категории"}],
                recovery="correct_input",
            )
        answer = existing.get(qid)
        if answer is None:
            answer = TestAttemptAnswer(attempt_id=attempt.id, question_id=qid, option_id=opt_id)
            db.add(answer)
            existing[qid] = answer
        else:
            answer.option_id = opt_id
    await db.commit()


def compute_block_result(attempt: TestAttempt) -> dict[int, tuple[int, int]]:
    """{block: (correct, total)} по 2 задания в блоке."""
    by_block: dict[int, tuple[int, int]] = {
        1: (attempt.block1_correct, 0),
        2: (attempt.block2_correct, 0),
        3: (attempt.block3_correct, 0),
    }
    total_per_block = attempt.total_count // len(BLOCKS) if attempt.total_count else 2
    return {b: (by_block[b][0], total_per_block) for b in BLOCKS}


async def submit_attempt(
    db: AsyncSession,
    attempt: TestAttempt,
    settings: Settings,
) -> TestAttempt:
    """Подсчёт результата, блоки, подтверждение категории (FR-13).

    Вызывается только для активной попытки с полным набором ответов;
    защита от повторной отправки реализована проверкой статуса.
    """
    if attempt.status == TestAttemptStatus.COMPLETED:
        raise errors.Problem(
            409, errors.INVALID_STATE, errors.E12_STATE, "Попытка уже отправлена",
            detail="Повторная отправка результата запрещена.", recovery="none",
        )
    if mark_expired(attempt):
        await db.commit()
        raise errors.Problem(
            409, errors.INVALID_STATE, errors.E13_TIME, "Время попытки истекло",
            detail="Серверный таймер попытки истёк. Результат не засчитан.",
            recovery="retry",
        )

    questions = await questions_for_category(db, attempt.specialization_id, attempt.grade_level)
    q_by_id = {q.id: q for q in questions}
    answer_rows = attempt.answers

    correct_count = 0
    block_correct = {b: 0 for b in BLOCKS}
    block_total = {b: 0 for b in BLOCKS}
    total = len(questions)
    for row in answer_rows:
        question = q_by_id.get(row.question_id)
        if question is None:
            continue
        block_total[question.block] = block_total.get(question.block, 0) + 1
        option = next((o for o in question.options if o.id == row.option_id), None)
        if option is not None and option.is_correct:
            correct_count += 1
            block_correct[question.block] = block_correct.get(question.block, 0) + 1

    score_percent = round(correct_count * 100 / total) if total else 0
    blocks_passed = all(
        block_total.get(b, 0) > 0
        and block_correct.get(b, 0) * 100 // block_total[b] >= settings.test_pass_block_percent
        for b in BLOCKS
    )
    passed = score_percent >= settings.test_pass_total_percent and blocks_passed

    attempt.status = TestAttemptStatus.COMPLETED
    attempt.submitted_at = datetime.now(UTC)
    attempt.correct_count = correct_count
    attempt.total_count = total
    attempt.score_percent = score_percent
    attempt.block1_correct = block_correct.get(1, 0)
    attempt.block2_correct = block_correct.get(2, 0)
    attempt.block3_correct = block_correct.get(3, 0)

    grade = await grade_by_level(db, attempt.grade_level) if passed else None
    attempt.result_grade_id = grade.id if grade else None
    if grade is not None:
        await apply_result_category(db, attempt.candidate_id, attempt.specialization_id, grade, attempt)
    return attempt


async def apply_result_category(
    db: AsyncSession,
    candidate_id: uuid.UUID,
    specialization_id: uuid.UUID,
    grade: Grade,
    attempt: TestAttempt,
) -> ConfirmedCategory:
    """Подтверждение выбранной категории.

    Та же категория — обновляем источник попытки (дата назначения не меняется).
    Другая — деактивируем старую и фиксируем новую (confirmed_at = now).
    """
    active = await active_category(db, candidate_id)
    if active is not None and active.specialization_id == specialization_id and active.grade_id == grade.id:
        active.source_attempt_id = attempt.id
        return active
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


def build_attempt_result(attempt: TestAttempt, settings: Settings, message: str) -> dict:
    blocks = [
        {"block": b, "correct": correct, "total": total}
        for b, (correct, total) in compute_block_result(attempt).items()
    ]
    next_at = next_attempt_at(attempt, settings)
    return {
        "attempt_id": attempt.id,
        "specialization_id": attempt.specialization_id,
        "specialization_name": attempt.specialization.name if attempt.specialization else "",
        "grade_code": attempt.result_grade.code if attempt.result_grade else None,
        "grade_name": attempt.result_grade.name if attempt.result_grade else None,
        "status": attempt.status.value,
        "correct_count": attempt.correct_count,
        "total_count": attempt.total_count,
        "score_percent": attempt.score_percent or 0,
        "block_results": blocks,
        "passed": attempt.result_grade_id is not None,
        "next_attempt_at": next_at.isoformat() if next_at else None,
        "message": message,
    }