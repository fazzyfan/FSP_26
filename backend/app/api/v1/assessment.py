"""Эндпоинты теста и подтверждённой категории кандидата (FR-08..FR-13).

Поток:
- POST /tests/{specialization_id}/start  — создание/продолжение активной попытки
  с серверным таймером 20 минут;
- PUT  /attempts/{attempt_id}/answers   — сохранение ответов по мере выбора;
- GET  /attempts/{attempt_id}           — восстановление после перезагрузки;
- POST /attempts/{attempt_id}/submit    — подсчёт, блоки, категория.

Защита: одна активная попытка; повторная отправка и перезапись завершённых
попыток отклоняются (409); правильные ответы клиенту не передаются.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_csrf, require_roles
from app.core import errors
from app.core.config import get_settings
from app.db.base import get_db
from app.models.account import Account, Role
from app.models.assessment import (
    ConfirmedCategory,
    TestAttempt,
    TestAttemptAnswer,
    TestAttemptStatus,
    TestQuestion,
)
from app.models.candidate import CandidateProfile
from app.models.reference import Grade, Specialization
from app.schemas.assessment import (
    ActiveAttemptOut,
    AnswerIn,
    AssessmentSummaryOut,
    AttemptAnswersIn,
    AttemptResultOut,
    AttemptStateOut,
    ConfirmedCategoryOut,
    QuestionOut,
    StartAttemptIn,
    TestGradeInfoOut,
    TestInfoOut,
)
from app.services import assessment as assessment_service

router = APIRouter(prefix="/candidate/assessment", tags=["assessment"])

CandidateDep = Depends(require_roles(Role.CANDIDATE))

GRADE_CODES = {"junior": 1, "middle": 2}


async def _own_profile(db: AsyncSession, account: Account) -> CandidateProfile:
    profile = await db.scalar(select(CandidateProfile).where(CandidateProfile.account_id == account.id))
    if profile is None:
        raise errors.Problem(
            409, errors.INVALID_STATE, errors.E12_STATE, "Сначала заполните профиль",
            detail="Для прохождения теста заполните и опубликуйте профиль кандидата.",
            recovery="correct_input",
        )
    return profile


def _category_out(c: ConfirmedCategory) -> ConfirmedCategoryOut:
    return ConfirmedCategoryOut(
        id=c.id,
        specialization_id=c.specialization_id,
        specialization_name=c.specialization.name,
        grade_code=c.grade.code,
        grade_name=c.grade.name,
        confirmed_at=c.confirmed_at.isoformat(),
    )


def _question_out(q: TestQuestion) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        text=q.text,
        block=q.block,
        options=[{"id": o.id, "text": o.text} for o in q.options],
    )


async def _attempt_state(db: AsyncSession, attempt: TestAttempt) -> AttemptStateOut:
    """Состояние попытки; просроченная попытка помечается EXPIRED."""
    was_expired = assessment_service.mark_expired(attempt)
    if was_expired:
        await db.commit()
    grade = await assessment_service.grade_by_level(db, attempt.grade_level)
    questions = await assessment_service.questions_for_category(db, attempt.specialization_id, attempt.grade_level)
    answers = [
        AnswerIn(question_id=a.question_id, option_id=a.option_id)
        for a in sorted(attempt.answers, key=lambda x: str(x.question_id))
    ]
    return AttemptStateOut(
        attempt_id=attempt.id,
        specialization_id=attempt.specialization_id,
        specialization_name=attempt.specialization.name if attempt.specialization else "",
        grade_code=grade.code if grade else "",
        grade_name=grade.name if grade else "",
        status=attempt.status.value,
        started_at=attempt.started_at.isoformat(),
        expires_at=attempt.expires_at.isoformat(),
        remaining_seconds=assessment_service.remaining_seconds(attempt),
        questions=[_question_out(q) for q in questions],
        answers=answers,
    )


async def _own_attempt(db: AsyncSession, account: Account, attempt_id: uuid.UUID) -> TestAttempt:
    profile = await _own_profile(db, account)
    attempt = await db.get(TestAttempt, attempt_id)
    if attempt is None or attempt.candidate_id != profile.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Попытка не найдена", recovery="none")
    return attempt


@router.get("", response_model=AssessmentSummaryOut)
async def assessment_summary(
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> AssessmentSummaryOut:
    """Сводка: категория, активная попытка, последний результат, доступные тесты."""
    settings = get_settings()
    profile = await db.scalar(select(CandidateProfile).where(CandidateProfile.account_id == account.id))

    category = None
    active_attempt = None
    last_attempt = None
    next_attempt_at = None
    if profile is not None:
        category = await assessment_service.active_category(db, profile.id)

        active = await assessment_service.active_in_progress_attempt(db, profile.id)
        if active is not None:
            if assessment_service.mark_expired(active):
                await db.commit()
            else:
                grade = await assessment_service.grade_by_level(db, active.grade_level)
                active_attempt = ActiveAttemptOut(
                    attempt_id=active.id,
                    specialization_id=active.specialization_id,
                    specialization_name=active.specialization.name if active.specialization else "",
                    grade_code=grade.code if grade else "",
                    grade_name=grade.name if grade else "",
                    expires_at=active.expires_at.isoformat(),
                    remaining_seconds=assessment_service.remaining_seconds(active),
                )

        last_attempt = await db.scalar(
            select(TestAttempt)
            .where(
                TestAttempt.candidate_id == profile.id,
                TestAttempt.status.in_([TestAttemptStatus.COMPLETED, TestAttemptStatus.EXPIRED]),
            )
            .order_by(TestAttempt.submitted_at.desc())
            .limit(1)
        )
        nxt = assessment_service.next_attempt_at(last_attempt, settings)
        if nxt is not None and datetime.now(UTC) < nxt:
            next_attempt_at = nxt.isoformat()

    # Доступные тесты: специализация × грейд (4 категории)
    rows = (
        await db.execute(
            select(
                Specialization.id,
                Specialization.name,
                TestQuestion.grade_level,
                func.count(TestQuestion.id),
            )
            .join(TestQuestion, TestQuestion.specialization_id == Specialization.id)
            .where(TestQuestion.is_active.is_(True))
            .group_by(Specialization.id, Specialization.name, TestQuestion.grade_level)
            .order_by(Specialization.name, TestQuestion.grade_level)
        )
    ).all()

    tests: list[TestInfoOut] = []
    grades_cache: dict[int, Grade] = {}
    for spec_id, spec_name, grade_level, cnt in rows:
        if spec_id not in {t.specialization_id for t in tests}:
            tests.append(
                TestInfoOut(specialization_id=spec_id, specialization_name=spec_name, grades=[], questions_count=0)
            )
        grade = grades_cache.get(grade_level)
        if grade is None:
            grade = await assessment_service.grade_by_level(db, grade_level)
            grades_cache[grade_level] = grade
        item = next(t for t in tests if t.specialization_id == spec_id)
        item.grades.append(
            TestGradeInfoOut(
                grade_code=grade.code if grade else "",
                grade_name=grade.name if grade else "",
                questions_count=int(cnt),
            )
        )
        item.questions_count += int(cnt)

    return AssessmentSummaryOut(
        category=_category_out(category) if category else None,
        active_attempt=active_attempt,
        last_attempt=(
            assessment_service.build_attempt_result(last_attempt, settings, "")
            if last_attempt
            else None
        ),
        next_attempt_at=next_attempt_at,
        tests=tests,
    )


@router.post(
    "/tests/{specialization_id}/start",
    response_model=AttemptStateOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def start_test(
    specialization_id: uuid.UUID,
    payload: StartAttemptIn,
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> AttemptStateOut:
    """Старт теста выбранной категории (специализация + грейд).

    Идемпотентно: если активная попытка той же категории уже есть — возвращает её.
    Одна активная попытка; таймер 20 минут отсчитывается на сервере.
    """
    settings = get_settings()
    profile = await _own_profile(db, account)
    specialization = await db.get(Specialization, specialization_id)
    if specialization is None:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Специализация не найдена", recovery="none")
    grade_level = GRADE_CODES.get(payload.grade)
    if grade_level is None:
        raise errors.Problem(422, errors.VALIDATION_FAILED, errors.E02_FORMAT,
                             "Некорректный грейд", recovery="correct_input")

    questions = await assessment_service.questions_for_category(db, specialization_id, grade_level)
    if len(questions) != 6:
        raise errors.Problem(
            409, errors.INVALID_STATE, errors.E12_STATE, "Тест по этой категории не готов",
            detail="Нужно 6 заданий в 3 блоках. Обратитесь к администратору.", recovery="retry",
        )

    attempt = await assessment_service.start_attempt(db, profile.id, specialization_id, grade_level, settings)
    return await _attempt_state(db, attempt)


@router.get("/attempts/{attempt_id}", response_model=AttemptStateOut)
async def get_attempt(
    attempt_id: uuid.UUID,
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> AttemptStateOut:
    """Восстановление попытки после перезагрузки страницы."""
    attempt = await _own_attempt(db, account, attempt_id)
    return await _attempt_state(db, attempt)


@router.put(
    "/attempts/{attempt_id}/answers",
    response_model=AttemptStateOut,
    dependencies=[Depends(require_csrf)],
)
async def save_attempt_answers(
    attempt_id: uuid.UUID,
    payload: AttemptAnswersIn,
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> AttemptStateOut:
    """Сохранение ответов по мере выбора (upsert). Закрытая попытка — 409."""
    attempt = await _own_attempt(db, account, attempt_id)
    questions = await assessment_service.questions_for_category(db, attempt.specialization_id, attempt.grade_level)
    valid_ids = {q.id for q in questions}

    # Дубли в одном запросе не допускаются
    seen: set[uuid.UUID] = set()
    pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
    for a in payload.answers:
        if a.question_id in seen:
            raise errors.Problem(
                422, errors.VALIDATION_FAILED, errors.E02_FORMAT, "Дублирующийся ответ",
                errors=[{"field": "answers", "code": "DUPLICATE_ANSWER", "error_class": "E02",
                         "message": "На каждый вопрос — один ответ"}], recovery="correct_input",
            )
        seen.add(a.question_id)
        pairs.append((a.question_id, a.option_id))

    await assessment_service.save_answers(db, attempt, pairs, valid_ids)
    await db.refresh(attempt)
    return await _attempt_state(db, attempt)


@router.post(
    "/attempts/{attempt_id}/submit",
    response_model=AttemptResultOut,
    dependencies=[Depends(require_csrf)],
)
async def submit_attempt(
    attempt_id: uuid.UUID,
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> AttemptResultOut:
    """Проверка ответов, блоки и подтверждение категории (FR-13).

    Только активная попытка; повторная отправка (после потери связи) — 409,
    старые данные новыми запросами не перезаписываются.
    """
    settings = get_settings()
    attempt = await _own_attempt(db, account, attempt_id)
    if attempt.status != TestAttemptStatus.IN_PROGRESS:
        raise errors.Problem(
            409, errors.INVALID_STATE, errors.E12_STATE, "Попытка уже завершена",
            detail="Повторная отправка результата запрещена.", recovery="none",
        )

    questions = await assessment_service.questions_for_category(db, attempt.specialization_id, attempt.grade_level)
    if not questions:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Тест по этой категории не готов", recovery="retry")

    answered = {a.question_id for a in attempt.answers}
    missing = {q.id for q in questions} - answered
    if missing:
        raise errors.Problem(
            422, errors.VALIDATION_FAILED, errors.E01_REQUIRED, "Не все вопросы отвечены",
            errors=[{"field": "answers", "code": "MISSING_ANSWER", "error_class": "E01",
                     "message": f"Ответьте на все вопросы (не отвечен {len(missing)})"}],
            recovery="correct_input",
        )

    attempt = await assessment_service.submit_attempt(db, attempt, settings)
    await db.commit()
    await db.refresh(attempt)

    if attempt.result_grade_id is not None:
        message = (
            f"Категория подтверждена: {attempt.specialization.name}, "
            f"{attempt.result_grade.name}. Сумма ≥ {settings.test_pass_total_percent}%, "
            "каждый блок ≥ 50%."
        )
    else:
        message = (
            f"Тест не пройден: {attempt.correct_count} из {attempt.total_count} "
            f"({attempt.score_percent}%). Нужно ≥ {settings.test_pass_total_percent}% суммарно "
            "и ≥ 50% в каждом блоке. Пересдача этой категории доступна через 24 ч."
        )
    result = assessment_service.build_attempt_result(attempt, settings, message)
    return AttemptResultOut(**result)