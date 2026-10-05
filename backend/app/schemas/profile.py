"""Схемы профиля кандидата (FR-05) и компании (FR-16)."""

from __future__ import annotations

import unicodedata
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.auth import validate_full_name


def _validate_experience(v: int) -> int:
    if v < 0 or v > 720:
        raise ValueError("Стаж должен быть от 0 до 720 месяцев")
    return v


class CandidateProfileIn(BaseModel):
    full_name: str
    phone: str | None = Field(default=None, max_length=32)
    experience_months: int = Field(default=0, ge=0, le=720)
    role_ids: list[uuid.UUID] = Field(min_length=1)
    skill_ids: list[uuid.UUID] = Field(min_length=1)
    claimed_level_id: uuid.UUID | None = None
    soft_skills: list[str] = Field(default_factory=list)
    about: str | None = Field(default=None, max_length=3000)
    is_published: bool = False
    show_fsp: bool = False
    fsp_member_id: str | None = Field(default=None, max_length=64)
    version: int = Field(default=1, ge=1)

    @field_validator("full_name")
    @classmethod
    def name(cls, v: str) -> str:
        return validate_full_name(v)

    @field_validator("soft_skills")
    @classmethod
    def soft_skills_clean(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for s in v:
            s = unicodedata.normalize("NFC", s.strip())
            if not s:
                continue
            if len(s) > 100:
                raise ValueError("Название софт-скилла не длиннее 100 символов")
            cleaned.append(s)
        return cleaned


class CandidateProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: str
    phone: str | None
    contact_email: str
    experience_months: int
    claimed_level: str | None = None
    claimed_level_code: str | None = None
    roles: list[str]
    skills: list[str]
    soft_skills: list[str]
    about: str | None
    is_published: bool
    show_fsp: bool
    fsp_member_id: str | None
    version: int
    updated_at: str | None = None


class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    industry_id: uuid.UUID | None = None
    description: str | None = Field(default=None, min_length=10, max_length=3000)
    contact_email: EmailStr
    website: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=32)
    version: int = Field(default=1, ge=1)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    industry_id: str | None
    industry_name: str | None
    description: str | None
    contact_email: str
    website: str | None
    phone: str | None
    version: int


class EmployerNeedIn(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    tasks_text: str = Field(min_length=20, max_length=3000)
    industry_id: uuid.UUID | None = None
    specialization_id: uuid.UUID | None = None
    grade_ids: list[uuid.UUID] = Field(min_length=1)
    skill_ids: list[uuid.UUID] = Field(min_length=1)


class EmployerNeedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    title: str
    tasks_text: str
    industry_id: str | None
    specialization_id: str | None
    grade_ids: list[str]
    skill_ids: list[str]
    created_at: str | None