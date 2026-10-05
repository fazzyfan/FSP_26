"""Pydantic-схемы аутентификации (FR-01, FR-02)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.account import Role

# Допустимые символы ФИО: Unicode-буквы, диакритика, пробелы, дефисы, апострофы (каталог E02)
_NAME_CHARS = re.compile(r"^[\w\s'’-]+$", re.UNICODE)


def validate_full_name(value: str) -> str:
    """Единый валидатор ФИО (E02 NAME_FORMAT): NFC, без краевых пробелов, 2..150."""
    import unicodedata

    value = unicodedata.normalize("NFC", value).strip()
    if len(value) < 2 or len(value) > 150:
        raise ValueError("ФИО должно быть от 2 до 150 символов")
    allowed = {"-", "'", "’", " ", " "}
    for ch in value:
        cat = unicodedata.category(ch)
        if ch in allowed:
            continue
        if not (cat[0] == "L" or cat[0] == "M"):
            raise ValueError("ФИО может содержать только буквы, пробелы, дефисы и апострофы")
    return value


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    role: Role
    consent_version: str = Field(min_length=1, max_length=16)
    consent_granted: bool

    @field_validator("password")
    @classmethod
    def check_password_length(cls, v: str) -> str:
        # FR-01: 12..128 символов, без усечения и нормализации
        if len(v) < 12 or len(v) > 128:
            raise ValueError("Пароль должен содержать от 12 до 128 символов")
        return v

    @field_validator("consent_granted")
    @classmethod
    def check_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Необходимо согласие на обработку персональных данных")
        return v


class RegisterOut(BaseModel):
    id: str
    email: str
    status: str
    detail: str


class ConfirmEmailIn(BaseModel):
    token: str = Field(min_length=8, max_length=200)


class ResendConfirmationIn(BaseModel):
    email: EmailStr


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: Role
    status: str