"""Безопасность: хеширование паролей Argon2id (NFR-02) и генерация токенов."""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Argon2id с уникальной солью (NFR-02)."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def generate_plain_token() -> str:
    """Opaque-токен для сессий и подтверждения email (храним только хеш)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Хеш opaque-токена для хранения в БД (NFR-02: токены не храним открытым текстом)."""
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()