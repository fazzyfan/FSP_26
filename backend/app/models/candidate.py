"""Профиль кандидата (FR-05): резюме, заявленные данные, приватность (FR-04)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.reference import candidate_roles, candidate_skills


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # ФИО: единое поле 2-150 символов (каталог ошибок E02 NAME_FORMAT)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Контактный email = подтверждённый email аккаунта (FR-05)
    experience_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0..720
    claimed_level_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True
    )
    soft_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)  # до 3000 символов
    # Приватность (FR-04): по умолчанию публикация выключена
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    show_fsp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fsp_member_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # ER-05
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    account: Mapped["Account"] = relationship(lazy="joined")  # type: ignore[name-defined]
    skills: Mapped[list["Skill"]] = relationship(secondary=candidate_skills, lazy="selectin")  # type: ignore[name-defined]
    roles: Mapped[list["RoleRef"]] = relationship(secondary=candidate_roles, lazy="selectin")  # type: ignore[name-defined]
    claimed_level: Mapped["Grade | None"] = relationship(lazy="joined")  # type: ignore[name-defined]