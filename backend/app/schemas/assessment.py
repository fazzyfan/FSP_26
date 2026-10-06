"""Схемы теста, попыток и подтверждённой категории (FR-08..FR-13).

Правильные ответы клиенту не передаются: вариант считается на сервере.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class QuestionOptionOut(BaseModel):
    id: uuid.UUID
    text: str


class QuestionOut(BaseModel):
    id: uuid.UUID
    text: str
    options: list[QuestionOptionOut]


class TestInfoOut(BaseModel):
    """Список доступных тестов по специализациям."""

    specialization_id: uuid.UUID
    specialization_name: str
    questions_count: int


class AnswerIn(BaseModel):
    question_id: uuid.UUID
    option_id: uuid.UUID


class AttemptSubmitIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1)


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
    status: str
    correct_count: int
    total_count: int
    score_percent: int
    passed: bool
    grade_code: str | None
    grade_name: str | None
    next_attempt_at: str | None
    message: str


class AssessmentSummaryOut(BaseModel):
    """Сводка по оценке для кабинета кандидата."""

    category: ConfirmedCategoryOut | None = None
    last_attempt: AttemptResultOut | None = None
    next_attempt_at: str | None = None
    tests: list[TestInfoOut]