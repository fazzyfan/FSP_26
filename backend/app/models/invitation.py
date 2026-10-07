"""Приглашения работодателя и открытие контактов (FR-23..FR-27).

Правила MVP:
- приглашение содержит обязательное описание (message), контакт работодателя
  (из профиля компании) и положительную зарплатную вилку (salary_from > 0);
- исходные условия фиксируются в строке приглашения и не изменяются;
- от одной компании кандидату может быть только одно «открытое» приглашение
  (pending или accepted) — partial unique index защищает и от одновременных запросов;
- контакты кандидата открываются конкретной компании только после явного
  согласия (accept + contacts_consented_at); доступ можно отозвать
  (contacts_revoked_at), повторное принятие не восстанавливает доступ.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


OPEN_STATUSES = (InvitationStatus.PENDING, InvitationStatus.ACCEPTED)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Invitation(Base):
    """Предложение работодателя кандидату с зарплатной вилкой и условиями (FR-23).

    Одна открытая пара (company, candidate) гарантируется частичным уникальным
    индексом: повторы и одновременные запросы не создают дублей (NFR-06).
    """

    __tablename__ = "invitations"
    __table_args__ = (
        Index(
            "uq_invitation_open_company_candidate",
            "company_id",
            "candidate_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'accepted')"),
        ),
        CheckConstraint("salary_from > 0", name="ck_invitations_salary_from_positive"),
        CheckConstraint("salary_to >= salary_from", name="ck_invitations_salary_range"),
        CheckConstraint("length(message) >= 10", name="ck_invitations_message_min_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    need_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("employer_needs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Исходные условия: обязательные и неизменяемые (FR-23)
    salary_from: Mapped[int] = mapped_column(Integer, nullable=False)
    salary_to: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=InvitationStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contacts_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Явное согласие кандидата на открытие контактов и отзыв доступа (FR-27)
    contacts_consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contacts_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    need: Mapped["EmployerNeed"] = relationship(lazy="joined")  # type: ignore[name-defined]
    company: Mapped["Company"] = relationship(lazy="joined")  # type: ignore[name-defined]
    candidate: Mapped["CandidateProfile"] = relationship(lazy="joined")  # type: ignore[name-defined]

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def contacts_available(self) -> bool:
        """Доступ к контактам: принято + явное согласие + не отозвано."""
        return (
            self.status == InvitationStatus.ACCEPTED
            and self.contacts_consented_at is not None
            and self.contacts_revoked_at is None
        )