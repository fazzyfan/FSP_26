"""FastAPI-зависимости: текущий аккаунт, роли, CSRF (FR-03, NFR-01, NFR-02)."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.config import get_settings
from app.db.base import get_db
from app.models.account import Account, Role
from app.services.auth import get_account_by_session


def _session_token(request: Request) -> str | None:
    return request.cookies.get(get_settings().session_cookie_name)


async def get_current_account(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Account:
    """Аутентификация по HttpOnly cookie сессии (NFR-02)."""
    token = _session_token(request)
    if not token:
        raise errors.Problem(401, errors.AUTH_REQUIRED, errors.E08_AUTH, "Требуется вход", recovery="reauthenticate")
    account = await get_account_by_session(db, token)
    if account is None:
        raise errors.Problem(401, errors.AUTH_REQUIRED, errors.E08_AUTH, "Сессия недействительна или истекла", recovery="reauthenticate")
    return account


def require_roles(*roles: Role) -> Callable:
    """Проверка роли на сервере; скрытая кнопка не заменяет проверку прав (FR-03)."""

    async def dependency(account: Account = Depends(get_current_account)) -> Account:
        if account.role not in roles:
            raise errors.Problem(403, errors.ACCESS_DENIED, errors.E09_ACCESS, "Доступ запрещён", recovery="none")
        return account

    return dependency


def require_csrf(request: Request) -> None:
    """Double-submit CSRF: заголовок X-CSRF-Token равен csrf-куке (NFR-02)."""
    settings = get_settings()
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get("X-CSRF-Token")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise errors.Problem(403, errors.CSRF_FAILED, errors.E09_ACCESS, "Проверка CSRF не пройдена", recovery="refresh")


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def get_candidate_id(account: Account) -> uuid.UUID:
    """Заглушка-маркер; профиль кандидата связан с account.id (владелец = аккаунт)."""
    return account.id