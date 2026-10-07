"""Модели оценки: вопросы теста, попытки, подтверждённая категория (FR-08..FR-13).

Правила MVP:
- 4 категории: специализация (Python backend / Системный анализ) × грейд
  (Junior / Middle); кандидат выбирает категорию перед тестом;
- тест выбранной категории: 6 заданий в 3 блоках (по 2 задания);
- категория подтверждается при суммарном результате >= 70% и >= 50%
  в каждом блоке;
- одна активная попытка; серверный таймер 20 минут (expires_at);
- пересдача той же категории — через 24 часа, смена подтверждённой — через 90 дней.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TestAttemptStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"


def utcnow() -> datetime:
    return datetime.now(UTC)


class TestQuestion(Base):
    """Вопрос теста по специализации и грейду. block — раздел теста (1..3)."""

    __tablename__ = "test_questions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    specialization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("specializations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grade_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 1=Junior, 2=Middle
    block: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # раздел 1..3
    text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    options: Mapped[list["TestQuestionOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TestQuestionOption.sort_order",
    )


class TestQuestionOption(Base):
    """Вариант ответа. is_correct не отдаётся клиенту до отправки ответов."""

    __tablename__ = "test_question_options"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question: Mapped[TestQuestion] = relationship(back_populates="options")


class TestAttempt(Base):
    """Попытка теста выбранной категории.

    Попытка создаётся на старте (status=in_progress) и живёт до expires_at
    (серверный таймер 20 минут). Ответы сохраняются по мере выбора и
    восстанавливаются после перезагрузки. После submit попытка закрыта.
    """

    __tablename__ = "test_attempts"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    specialization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("specializations.id", ondelete="RESTRICT"), nullable=False
    )
    grade_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # выбранная категория
    status: Mapped[TestAttemptStatus] = mapped_column(
        Enum(TestAttemptStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=TestAttemptStatus.IN_PROGRESS,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Результаты по блокам (по 2 задания в блоке)
    block1_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    block2_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    block3_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_grade_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True
    )

    answers: Mapped[list["TestAttemptAnswer"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan", lazy="selectin"
    )
    result_grade: Mapped["Grade | None"] = relationship(lazy="joined")  # type: ignore[name-defined]
    specialization: Mapped["Specialization"] = relationship(lazy="joined")  # type: ignore[name-defined]


class TestAttemptAnswer(Base):
    """Ответ кандидата на вопрос в рамках попытки (один на вопрос, upsert)."""

    __tablename__ = "test_attempt_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_attempt_answer_question"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_questions.id", ondelete="CASCADE"), nullable=False
    )
    option_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_question_options.id", ondelete="CASCADE"), nullable=False
    )

    attempt: Mapped[TestAttempt] = relationship(back_populates="answers")


class ConfirmedCategory(Base):
    """Подтверждённая категория: специализация + грейд (FR-13).

    Одна активная категория на кандидата (partial unique index по is_active);
    старые результаты хранятся с is_active=False. Смена доступна через
    90 дней после назначения или смены (confirmed_at).
    """

    __tablename__ = "confirmed_categories"
    __table_args__ = (
        Index(
            "uq_confirmed_categories_active",
            "candidate_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    specialization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("specializations.id", ondelete="RESTRICT"), nullable=False
    )
    grade_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("grades.id", ondelete="RESTRICT"), nullable=False
    )
    source_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_attempts.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    specialization: Mapped["Specialization"] = relationship(lazy="joined")  # type: ignore[name-defined]
    grade: Mapped["Grade"] = relationship(lazy="joined")  # type: ignore[name-defined]