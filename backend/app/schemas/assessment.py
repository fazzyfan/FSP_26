"""Схемы теста, попыток и подтверждённой категории (FR-08..FR-13).

Правильные ответы клиенту не передаются: вариант считается на сервере.
Попытка создаётся на старте, ответы сохраняются и восстанавливаются.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class QuestionOptionOut(BaseModel):
    id: uuid.UUID
    text: str


class QuestionOut(BaseModel):
    id: uuid.UUID
    text: str
    block: int  # раздел 1..3
    options: list[QuestionOptionOut]


class TestGradeInfoOut(BaseModel):
    """Доступность категории по грейду (количество заданий)."""

    grade_code: str
    grade_name: str
    questions_count: int


class TestInfoOut(BaseModel):
    """Список доступных тестов по специализациям (4 категории)."""

    specialization_id: uuid.UUID
    specialization_name: str
    grades: list[TestGradeInfoOut]
    questions_count: int


class StartAttemptIn(BaseModel):
    grade: Literal["junior", "middle"]


class AnswerIn(BaseModel):
    question_id: uuid.UUID
    option_id: uuid.UUID


class AttemptAnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(default_factory=list)


class AttemptStateOut(BaseModel):
    """Состояние попытки: вопросы, сохранённые ответы, оставшееся время."""

    attempt_id: uuid.UUID
    specialization_id: uuid.UUID
    specialization_name: str
    grade_code: str
    grade_name: str
    status: str
    started_at: str
    expires_at: str
    remaining_seconds: int
    questions: list[QuestionOut]
    answers: list[AnswerIn]


class BlockResultOut(BaseModel):
    block: int
    correct: int
    total: int


class ConfirmedCategoryOut(BaseModel):
    id: uuid.UUID
    specialization_id: uuid.UUID
    specialization_name: str
    grade_code: str
    grade_name: str
    confirmed_at: str


class AttemptResultOut(BaseModel):
    attempt_id: uuid.UUID
    specialization_id: uuid.UUID
    specialization_name: str
    grade_code: str | None
    grade_name: str | None
    status: str
    correct_count: int
    total_count: int
    score_percent: int
    block_results: list[BlockResultOut]
    passed: bool
    next_attempt_at: str | None
    message: str


class ActiveAttemptOut(BaseModel):
    """Активная попытка для восстановления после перезагрузки."""

    attempt_id: uuid.UUID
    specialization_id: uuid.UUID
    specialization_name: str
    grade_code: str
    grade_name: str
    expires_at: str
    remaining_seconds: int


class AssessmentSummaryOut(BaseModel):
    """Сводка по оценке для кабинета кандидата."""

    category: ConfirmedCategoryOut | None = None
    active_attempt: ActiveAttemptOut | None = None
    last_attempt: AttemptResultOut | None = None
    next_attempt_at: str | None = None
    tests: list[TestInfoOut]