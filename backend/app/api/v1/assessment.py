"""Эндпоинты теста и подтверждённой категории кандидата (FR-08..FR-13)."""

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
from app.models.reference import Specialization
from app.schemas.assessment import (
    AnswerIn,
    AssessmentSummaryOut,
    AttemptResultOut,
    AttemptSubmitIn,
    ConfirmedCategoryOut,
    QuestionOut,
    TestInfoOut,
)
from app.services import assessment as assessment_service

router = APIRouter(prefix="/candidate/assessment", tags=["assessment"])

CandidateDep = Depends(require_roles(Role.CANDIDATE))


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


@router.get("", response_model=AssessmentSummaryOut)
async def assessment_summary(
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> AssessmentSummaryOut:
    """Сводка: текущая категория, последняя попытка, доступность тестов."""
    settings = get_settings()
    profile = await db.scalar(select(CandidateProfile).where(CandidateProfile.account_id == account.id))

    category = None
    last_attempt = None
    next_attempt_at = None
    if profile is not None:
        category = await assessment_service.active_category(db, profile.id)
        last_attempt = await assessment_service.last_completed_attempt(db, profile.id)
        nxt = assessment_service.next_attempt_at(last_attempt, settings)
        if nxt is not None and datetime.now(UTC) < nxt:
            next_attempt_at = nxt.isoformat()

    rows = (
        await db.execute(
            select(Specialization.id, Specialization.name, func.count(TestQuestion.id))
            .join(TestQuestion, TestQuestion.specialization_id == Specialization.id)
            .where(TestQuestion.is_active.is_(True))
            .group_by(Specialization.id, Specialization.name)
            .order_by(Specialization.name)
        )
    ).all()
    tests = [
        TestInfoOut(specialization_id=row[0], specialization_name=row[1], questions_count=int(row[2]))
        for row in rows
    ]

    return AssessmentSummaryOut(
        category=_category_out(category) if category else None,
        last_attempt=(
            assessment_service.build_attempt_result(
                last_attempt,
                settings,
                assessment_service.next_attempt_at(last_attempt, settings) or datetime.now(UTC),
                "",
            )
            if last_attempt
            else None
        ),
        next_attempt_at=next_attempt_at,
        tests=tests,
    )


@router.get("/tests/{specialization_id}/questions", response_model=list[QuestionOut])
async def test_questions(
    specialization_id: uuid.UUID,
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> list[QuestionOut]:
    """Вопросы теста без правильных ответов (вариант подсчитывается на сервере)."""
    if await db.get(Specialization, specialization_id) is None:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS, "Специализация не найдена", recovery="none")
    questions = await assessment_service.questions_for_specialization(db, specialization_id)
    if not questions:
        raise errors.Problem(
            409, errors.INVALID_STATE, errors.E12_STATE, "Тест по этой специализации не готов",
            detail="Вопросы ещё не загружены. Попробуйте позже.", recovery="retry",
        )
    return [
        QuestionOut(
            id=q.id,
            text=q.text,
            options=[{"id": o.id, "text": o.text} for o in q.options],
        )
        for q in questions
    ]


@router.post(
    "/tests/{specialization_id}/submit",
    response_model=AttemptResultOut,
    dependencies=[Depends(require_csrf)],
)
async def submit_test(
    specialization_id: uuid.UUID,
    payload: AttemptSubmitIn,
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> AttemptResultOut:
    """Проверка ответов, грейдирование (D-02..D-06) и обновление категории (FR-13).

    ER-13: повтор до истечения кулдауна отклоняется 409.
    """
    settings = get_settings()
    profile = await _own_profile(db, account)
    specialization = await db.get(Specialization, specialization_id)
    if specialization is None:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS, "Специализация не найдена", recovery="none")

    questions = await assessment_service.questions_for_specialization(db, specialization_id)
    if not questions:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE, "Тест по этой специализации не готов", recovery="retry")

    # Допуск: кулдаун после последней попытки
    last = await assessment_service.last_completed_attempt(db, profile.id)
    nxt = assessment_service.next_attempt_at(last, settings)
    if nxt is not None and datetime.now(UTC) < nxt:
        raise errors.Problem(
            409, errors.INVALID_STATE, errors.E13_TIME, "Повтор теста пока недоступен",
            detail=f"Следующая попытка доступна с {nxt.isoformat()}.",
            recovery="wait", extra={"next_allowed_at": nxt.isoformat()},
        )

    # Валидация ответов: все вопросы, без дублей, варианты принадлежат вопросам
    q_by_id = {q.id: q for q in questions}
    q_ids = set(q_by_id.keys())
    answer_map: dict[uuid.UUID, uuid.UUID] = {}
    for a in payload.answers:
        if a.question_id not in q_ids:
            raise errors.Problem(
                422, errors.VALIDATION_FAILED, errors.E04_REFERENCE, "Неизвестный вопрос",
                errors=[{"field": "answers", "code": "REFERENCE_INVALID", "error_class": "E04",
                         "message": "Вопрос не входит в тест"}], recovery="correct_input",
            )
        if a.question_id in answer_map:
            raise errors.Problem(
                422, errors.VALIDATION_FAILED, errors.E02_FORMAT, "Дублирующийся ответ",
                errors=[{"field": "answers", "code": "DUPLICATE_ANSWER", "error_class": "E02",
                         "message": "На каждый вопрос — один ответ"}], recovery="correct_input",
            )
        answer_map[a.question_id] = a.option_id
    missing = q_ids - set(answer_map.keys())
    if missing:
        raise errors.Problem(
            422, errors.VALIDATION_FAILED, errors.E01_REQUIRED, "Не все вопросы отвечены",
            errors=[{"field": "answers", "code": "MISSING_ANSWER", "error_class": "E01",
                     "message": f"Ответьте на все вопросы (не отвечен {len(missing)})"}], recovery="correct_input",
        )
    for qid, opt_id in answer_map.items():
        if not any(o.id == opt_id for o in q_by_id[qid].options):
            raise errors.Problem(
                422, errors.VALIDATION_FAILED, errors.E04_REFERENCE, "Неизвестный вариант ответа",
                errors=[{"field": "answers", "code": "REFERENCE_INVALID", "error_class": "E04",
                         "message": "Вариант не принадлежит вопросу"}], recovery="correct_input",
            )

    # Подсчёт
    correct_count = 0
    stored_answers: list[TestAttemptAnswer] = []
    for q in questions:
        chosen = answer_map[q.id]
        chosen_obj = next(o for o in q.options if o.id == chosen)
        if chosen_obj.is_correct:
            correct_count += 1
        stored_answers.append(TestAttemptAnswer(question_id=q.id, option_id=chosen))

    total = len(questions)
    score_percent = round(correct_count * 100 / total)
    level = assessment_service.grade_level_for_score(score_percent, settings)
    grade = await assessment_service.grade_by_level(db, level) if level else None

    attempt = TestAttempt(
        candidate_id=profile.id,
        specialization_id=specialization_id,
        status=TestAttemptStatus.COMPLETED,
        submitted_at=datetime.now(UTC),
        correct_count=correct_count,
        total_count=total,
        score_percent=score_percent,
        result_grade_id=grade.id if grade else None,
    )
    db.add(attempt)
    await db.flush()
    for ans in stored_answers:
        ans.attempt_id = attempt.id
    db.add_all(stored_answers)

    message = f"Тест не пройден: {correct_count} из {total}. Повтор доступен через {settings.test_retry_failed_hours} ч."
    if grade is not None:
        category = await assessment_service.apply_result_category(db, profile.id, specialization_id, grade, attempt)
        if category is not None:
            message = f"Категория подтверждена: {specialization.name}, {grade.name}."
        else:
            active = await assessment_service.active_category(db, profile.id)
            message = (
                f"Результат: {grade.name}. Текущая категория сохранена: "
                f"{active.specialization.name}, {active.grade.name} (без понижения)."
            )

    await db.commit()
    await db.refresh(attempt)

    next_at = assessment_service.compute_next_attempt_at(attempt, settings)
    result = assessment_service.build_attempt_result(attempt, settings, next_at, message)
    return AttemptResultOut(**result)