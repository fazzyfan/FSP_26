"""Модели учётных записей, согласий и сессий (FR-01..FR-04)."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(str, enum.Enum):
    """Роли пользователей (FR-01). Роль нельзя менять редактированием профиля."""

    CANDIDATE = "candidate"
    EMPLOYER = "employer"


class AccountStatus(str, enum.Enum):
    """Статусы учётной записи."""

    PENDING_EMAIL = "pending_email"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class ConsentType(str, enum.Enum):
    """Типы согласий (FR-01, FR-04)."""

    DATA_PROCESSING = "data_processing"
    PROFILE_PUBLICATION = "profile_publication"
    FSP_SHOWCASE = "fsp_showcase"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("email_normalized", name="uq_accounts_email"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, values_callable=lambda e: [m.value for m in e]), nullable=False)
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AccountStatus.PENDING_EMAIL,
    )
    consent_version: Mapped[str] = mapped_column(String(16), nullable=False)
    consent_granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirmation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    consent_events: Mapped[list["ConsentEvent"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", lazy="selectin"
    )
    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", lazy="selectin"
    )


class ConsentEvent(Base):
    """История согласий: пользователь, тип, версия, значение, время (FR-04)."""

    __tablename__ = "consent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_type: Mapped[ConsentType] = mapped_column(
        Enum(ConsentType, values_callable=lambda e: [m.value for m in e]), nullable=False
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    account: Mapped[Account] = relationship(back_populates="consent_events")


class AuthSession(Base):
    """Серверная сессия. Хранится хеш токена; выход инвалидирует сессию (NFR-02, D-06)."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped[Account] = relationship(back_populates="sessions")


class ConsentDoc(Base):
    """Тексты согласий с версиями (FR-01: согласие фиксируется с версией текста)."""

    __tablename__ = "consent_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)