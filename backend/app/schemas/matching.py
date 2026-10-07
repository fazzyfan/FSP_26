"""Схемы подбора кандидатов (FR-18..FR-22): карточка без контактов + пагинация."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class ScoreBreakdown(BaseModel):
    """Разбивка балла подбора: компетенции 60 / тест 30 / ФСП 10."""

    competencies: float
    test: float
    fsp: float


class MatchCandidateOut(BaseModel):
    candidate_id: uuid.UUID
    full_name: str
    specialization_name: str
    grade_code: str
    grade_name: str
    experience_months: int
    score: int
    score_breakdown: ScoreBreakdown
    matched_skills: list[str]
    reasons: list[str]


class MatchPageOut(BaseModel):
    items: list[MatchCandidateOut]
    total: int
    page: int
    page_size: int
    pages: int