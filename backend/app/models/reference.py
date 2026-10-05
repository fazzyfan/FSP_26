"""Справочники: отрасли, специализации, грейды, роли, навыки (FR-07, FR-19)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Table, Column
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Industry(Base):
    __tablename__ = "industries"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Specialization(Base):
    __tablename__ = "specializations"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Grade(Base):
    """Грейд + уровень для сортировки (D-01: Junior=1, Middle=2)."""

    __tablename__ = "grades"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[int] = mapped_column(nullable=False, unique=True)


class RoleRef(Base):
    """Справочник профессиональных ролей кандидата."""

    __tablename__ = "role_refs"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)


# Ассоциативные таблицы
candidate_skills = Table(
    "candidate_skills",
    Base.metadata,
    Column("candidate_id", PgUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", PgUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)

candidate_roles = Table(
    "candidate_roles",
    Base.metadata,
    Column("candidate_id", PgUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", PgUUID(as_uuid=True), ForeignKey("role_refs.id", ondelete="CASCADE"), primary_key=True),
)

need_grades = Table(
    "need_grades",
    Base.metadata,
    Column("need_id", PgUUID(as_uuid=True), ForeignKey("employer_needs.id", ondelete="CASCADE"), primary_key=True),
    Column("grade_id", PgUUID(as_uuid=True), ForeignKey("grades.id", ondelete="CASCADE"), primary_key=True),
)

need_skills = Table(
    "need_skills",
    Base.metadata,
    Column("need_id", PgUUID(as_uuid=True), ForeignKey("employer_needs.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", PgUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)