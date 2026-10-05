"""Эндпоинты аутентификации (FR-01..FR-03)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_account, new_csrf_token
from app.core.config import get_settings
from app.db.base import get_db
from app.models.account import Account, AccountStatus
from app.schemas.auth import ConfirmEmailIn, LoginIn, RegisterIn, RegisterOut, ResendConfirmationIn, SessionOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, session_token: str, csrf: str) -> None:
    settings = get_settings()
    common = {
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        httponly=True,
        max_age=settings.session_ttl_seconds,
        **common,
    )
    response.set_cookie(key=settings.csrf_cookie_name, value=csrf, httponly=False, max_age=settings.session_ttl_seconds, **common)


def _clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    for key in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(key=key, path="/")


@router.post("/register", response_model=RegisterOut, status_code=201)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)) -> RegisterOut:
    """FR-01: регистрация с ролью, согласием; статус pending_email; письмо с подтверждением."""
    account = await auth_service.register_account(
        db,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        consent_version=payload.consent_version,
    )
    return RegisterOut(
        id=str(account.id),
        email=account.email,
        status=account.status.value,
        detail="Аккаунт создан. Подтвердите email по ссылке из письма (действует 24 часа).",
    )


@router.post("/confirm-email", response_model=SessionOut)
async def confirm_email(payload: ConfirmEmailIn, db: AsyncSession = Depends(get_db)) -> SessionOut:
    """FR-02: активация аккаунта по одноразовой ссылке."""
    account = await auth_service.confirm_email(db, payload.token)
    return SessionOut(id=str(account.id), email=account.email, role=account.role, status=account.status.value)


@router.post("/resend-confirmation", status_code=202)
async def resend_confirmation(payload: ResendConfirmationIn, db: AsyncSession = Depends(get_db)) -> dict:
    """FR-02: повторное письмо (не чаще 1 раза в минуту, старый токен отменяется)."""
    await auth_service.resend_confirmation(db, payload.email)
    return {"detail": "Если аккаунт ожидает подтверждения, новое письмо отправлено."}


@router.post("/login", response_model=SessionOut)
async def login(payload: LoginIn, response: Response, db: AsyncSession = Depends(get_db)) -> SessionOut:
    """FR-03: вход; устанавливает HttpOnly cookie сессии и csrf-куку."""
    account = await auth_service.authenticate(db, payload.email, payload.password)
    token = await auth_service.create_session(db, account)
    _set_auth_cookies(response, token, new_csrf_token())
    return SessionOut(id=str(account.id), email=account.email, role=account.role, status=account.status.value)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> Response:
    """NFR-02: выход инвалидирует сессию и удаляет куки."""
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await auth_service.revoke_session(db, token)
    _clear_auth_cookies(response)
    response.status_code = 204
    return response


@router.get("/csrf", status_code=200)
async def get_csrf(response: Response) -> dict:
    """Выдаёт csrf-куку до логина (double-submit)."""
    settings = get_settings()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=new_csrf_token(),
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    return {"detail": "csrf установлен"}


@router.get("/session", response_model=SessionOut)
async def session_info(account: Account = Depends(get_current_account)) -> SessionOut:
    """Текущая сессия (используется фронтом для восстановления кабинета)."""
    return SessionOut(id=str(account.id), email=account.email, role=account.role, status=account.status.value)