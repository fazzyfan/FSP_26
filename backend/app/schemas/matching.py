"""Схемы подбора кандидатов (FR-18..FR-22): карточка без контактов."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class MatchCandidateOut(BaseModel):
    candidate_id: uuid.UUID
    full_name: str
    specialization_name: str
    grade_code: str
    grade_name: str
    experience_months: int
    score: int
    matched_skills: list[str]
    reasons: list[str]