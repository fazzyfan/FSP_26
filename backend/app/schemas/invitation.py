"""Схемы приглашений и открытия контактов (FR-23..FR-27)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class InvitationCreateIn(BaseModel):
    candidate_id: uuid.UUID
    salary_from: int | None = Field(default=None, ge=0, le=100_000_000)
    salary_to: int | None = Field(default=None, ge=0, le=100_000_000)
    message: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def check_salary(self) -> "InvitationCreateIn":
        if self.salary_from is not None and self.salary_to is not None and self.salary_from > self.salary_to:
            raise ValueError("salary_from не может превышать salary_to")
        return self


class RespondIn(BaseModel):
    decision: Literal["accept", "decline"]


class EmployerInvitationOut(BaseModel):
    """Проекция для работодателя (контакты не включены — FR-26)."""

    id: str
    need_id: str
    need_title: str
    candidate_id: str
    candidate_name: str
    salary_from: int | None
    salary_to: int | None
    message: str | None
    status: str
    created_at: str
    responded_at: str | None


class CandidateInvitationOut(BaseModel):
    """Проекция для кандидата."""

    id: str
    company_id: str
    company_name: str
    need_title: str
    salary_from: int | None
    salary_to: int | None
    message: str | None
    status: str
    created_at: str
    responded_at: str | None


class CandidateContactsOut(BaseModel):
    """Контакты кандидата — доступны только после принятия (FR-27)."""

    full_name: str
    phone: str | None
    email: str
    about: str | None