"""Приглашения работодателя и открытие контактов (FR-23..FR-27).

Контакты кандидата открываются работодателю только после принятия приглашения.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Invitation(Base):
    """Предложение работодателя кандидату по конкретной потребности с зарплатной вилкой."""

    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("need_id", "candidate_id", name="uq_invitation_need_candidate"),)

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
    salary_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=InvitationStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contacts_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    need: Mapped["EmployerNeed"] = relationship(lazy="joined")  # type: ignore[name-defined]
    company: Mapped["Company"] = relationship(lazy="joined")  # type: ignore[name-defined]
    candidate: Mapped["CandidateProfile"] = relationship(lazy="joined")  # type: ignore[name-defined]