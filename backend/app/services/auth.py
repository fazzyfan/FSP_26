"""Бизнес-логика аутентификации (FR-01..FR-03) с защитой по каталогу ошибок."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.config import get_settings
from app.core.security import generate_plain_token, hash_password, hash_token, verify_password
from app.models.account import Account, AccountStatus, AuthSession, ConsentDoc, ConsentEvent, ConsentType, Role
from app.services import mail

logger = logging.getLogger("fsp.auth")


def normalize_email(email: str) -> str:
    """Единая нормализация email аккаунтов (FR-01): без краевых пробелов, lowercase."""
    return email.strip().lower()


def _set_confirmation(account: Account, db: AsyncSession) -> str:
    """Создаёт одноразовый токен подтверждения (храним хеш, NFR-02) и шлёт письмо."""
    settings = get_settings()
    token = generate_plain_token()
    account.confirmation_token_hash = hash_token(token)
    account.confirmation_sent_at = datetime.now(UTC)
    account.confirmation_expires_at = datetime.now(UTC) + timedelta(seconds=settings.confirm_token_ttl_seconds)
    confirm_url = f"{settings.confirm_base_url}?token={token}"
    mail.send_mail(account.email, "Подтверждение email — ФСП обратный найм", mail.confirmation_email(confirm_url))
    return token


async def register_account(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    role: Role,
    consent_version: str,
) -> Account:
    """FR-01: создание учётной записи со статусом pending_email и согласием."""
    settings = get_settings()
    email_norm = normalize_email(email)

    doc = await db.scalar(select(ConsentDoc).where(ConsentDoc.code == "data_processing", ConsentDoc.version == consent_version))
    if doc is None:
        raise errors.Problem(
            422,
            errors.VALIDATION_FAILED,
            errors.E04_REFERENCE,
            "Неизвестная версия согласия",
            detail="Укажите актуальную версию согласия из справочника.",
            errors=[{"field": "consent_version", "code": "REFERENCE_INVALID", "error_class": "E04", "message": "Версия согласия не найдена"}],
            recovery="correct_input",
        )

    exists = await db.scalar(select(Account.id).where(Account.email_normalized == email_norm))
    if exists is not None:
        raise errors.Problem(
            409,
            errors.EMAIL_ALREADY_REGISTERED,
            errors.E11_CONCURRENCY,
            "Email уже зарегистрирован",
            detail="Для этого адреса уже создана учётная запись. Выполните вход или повторите подтверждение.",
            recovery="reauthenticate",
        )

    account = Account(
        email=email,
        email_normalized=email_norm,
        password_hash=hash_password(password),
        role=role,
        status=AccountStatus.PENDING_EMAIL,
        consent_version=consent_version,
        consent_granted_at=datetime.now(UTC),
    )
    db.add(account)
    db.add(
        ConsentEvent(
            account=account,
            consent_type=ConsentType.DATA_PROCESSING,
            version=consent_version,
            granted=True,
        )
    )
    await db.flush()
    _set_confirmation(account, db)
    await db.commit()
    await db.refresh(account)
    logger.info("Зарегистрирован аккаунт id=%s роль=%s", account.id, account.role.value)
    return account


async def confirm_email(db: AsyncSession, token: str) -> Account:
    """FR-02: активация по одноразовому токену (24 ч). Ошибка не активирует чужой аккаунт."""
    token_hash = hash_token(token)
    account = await db.scalar(select(Account).where(Account.confirmation_token_hash == token_hash))
    now = datetime.now(UTC)
    if account is None or account.status != AccountStatus.PENDING_EMAIL:
        raise errors.Problem(
            400, errors.TOKEN_INVALID, errors.E08_AUTH,
            "Ссылка подтверждения недействительна",
            detail="Ссылка использована, заменена или относится к уже активированному аккаунту.",
            recovery="reauthenticate",
        )
    if account.confirmation_expires_at is None or now >= account.confirmation_expires_at:
        raise errors.Problem(
            400, errors.TOKEN_INVALID, errors.E13_TIME,
            "Срок ссылки истёк",
            detail="Ссылка подтверждения действует 24 часа. Запросите новое письмо.",
            recovery="reauthenticate",
        )
    account.status = AccountStatus.ACTIVE
    account.confirmed_at = now
    account.confirmation_token_hash = None
    account.confirmation_expires_at = None
    await db.commit()
    await db.refresh(account)
    logger.info("Подтверждён email аккаунта id=%s", account.id)
    return account


async def resend_confirmation(db: AsyncSession, email: str) -> None:
    """FR-02: повторное письмо не чаще 1 раза в минуту; старый токен отменяется."""
    settings = get_settings()
    email_norm = normalize_email(email)
    account = await db.scalar(select(Account).where(Account.email_normalized == email_norm))
    if account is None:
        # Не раскрываем существование аккаунта (E09)
        return
    if account.status != AccountStatus.PENDING_EMAIL:
        return
    now = datetime.now(UTC)
    if account.confirmation_sent_at is not None:
        wait_until = account.confirmation_sent_at + timedelta(seconds=settings.resend_cooldown_seconds)
        if now < wait_until:
            retry = int((wait_until - now).total_seconds()) + 1
            raise errors.Problem(
                429, errors.RATE_LIMITED, errors.E18_LIMIT,
                "Слишком частые запросы",
                detail="Новое письмо можно запросить через минуту после предыдущего.",
                recovery="wait",
                extra={"retry_after_seconds": retry},
            )
    _set_confirmation(account, db)
    await db.commit()


async def authenticate(db: AsyncSession, email: str, password: str) -> Account:
    """FR-03: вход. Единый ответ на неверный пароль и неизвестный email (E08)."""
    email_norm = normalize_email(email)
    account = await db.scalar(select(Account).where(Account.email_normalized == email_norm))
    if account is None or not verify_password(password, account.password_hash):
        raise errors.Problem(
            401, errors.LOGIN_FAILED, errors.E08_AUTH,
            "Неверный email или пароль",
            detail="Проверьте введённые данные.",
            recovery="reauthenticate",
        )
    if account.status == AccountStatus.PENDING_EMAIL:
        raise errors.Problem(
            403, errors.EMAIL_UNCONFIRMED, errors.E12_STATE,
            "Email не подтверждён",
            detail="Подтвердите адрес почты, затем войдите.",
            recovery="reauthenticate",
        )
    if account.status == AccountStatus.DEACTIVATED:
        raise errors.Problem(
            403, errors.ACCESS_DENIED, errors.E09_ACCESS,
            "Доступ закрыт",
            detail="Учётная запись деактивирована.",
            recovery="contact_support",
        )
    account.last_login_at = datetime.now(UTC)
    await db.commit()
    return account


async def create_session(db: AsyncSession, account: Account) -> str:
    """Создаёт серверную сессию сроком до 24 часов (D-06); хранится хеш токена."""
    settings = get_settings()
    token = generate_plain_token()
    session = AuthSession(
        account_id=account.id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        last_used_at=datetime.now(UTC),
    )
    db.add(session)
    await db.commit()
    return token


async def revoke_session(db: AsyncSession, token: str) -> None:
    """NFR-02: выход инвалидирует сессию."""
    session = await db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        await db.commit()


async def get_account_by_session(db: AsyncSession, token: str) -> Account | None:
    """Возвращает аккаунт по действующей сессии или None."""
    session = await db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if session is None:
        return None
    now = datetime.now(UTC)
    if session.revoked_at is not None or session.expires_at <= now:
        return None
    account = await db.get(Account, session.account_id)
    if account is None or account.status != AccountStatus.ACTIVE:
        return None
    session.last_used_at = now
    await db.commit()
    return account