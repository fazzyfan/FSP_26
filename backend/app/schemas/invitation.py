"""Схемы приглашений и открытия контактов (FR-23..FR-27).

Приглашение обязано содержать описание (>= 10 символов), контакт работодателя
(берётся из профиля компании) и положительную зарплатную вилку.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class InvitationCreateIn(BaseModel):
    candidate_id: uuid.UUID
    salary_from: int = Field(ge=1, le=100_000_000, description="Нижняя граница вилки, > 0")
    salary_to: int = Field(ge=1, le=100_000_000, description="Верхняя граница вилки, > 0")
    message: str = Field(min_length=10, max_length=2000, description="Описание условий, >= 10 символов")

    @model_validator(mode="after")
    def check_salary(self) -> "InvitationCreateIn":
        if self.salary_from > self.salary_to:
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
    salary_from: int
    salary_to: int
    message: str
    status: str
    created_at: str
    responded_at: str | None
    contacts_consented_at: str | None
    contacts_revoked_at: str | None


class CandidateInvitationOut(BaseModel):
    """Проекция для кандидата: исходные условия + контакт работодателя (FR-23)."""

    id: str
    company_id: str
    company_name: str
    need_title: str
    salary_from: int
    salary_to: int
    message: str
    status: str
    created_at: str
    responded_at: str | None
    company_contact_email: str | None
    company_phone: str | None
    contacts_consented_at: str | None
    contacts_revoked_at: str | None


class CandidateContactsOut(BaseModel):
    """Контакты кандидата — доступны только после принятия (FR-27)."""

    full_name: str
    phone: str | None
    email: str
    about: str | None