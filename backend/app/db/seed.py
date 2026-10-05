"""Seed справочников и демонстрационных данных (FR-28).

Запуск: python -m app.db.seed
Идемпотентен: повторный запуск не создаёт дублей и не стирает пользовательские записи.
Демо-данные явно помечены как демонстрационные (FR-15, NFR-04).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import async_session_factory
from app.models.account import Account, AccountStatus, ConsentDoc, Role
from app.models.candidate import CandidateProfile
from app.models.employer import Company
from app.models.reference import Grade, Industry, RoleRef, Skill, Specialization

logger = logging.getLogger("fsp.seed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

DEMO_PASSWORD = "DemoPass2026!"


async def _get_or_create(session: AsyncSession, model, **kwargs):
    existing = await session.scalar(select(model).where(*[getattr(model, k) == v for k, v in kwargs.items()]))
    if existing is not None:
        return existing
    obj = model(**kwargs)
    session.add(obj)
    return obj


async def seed_references(session: AsyncSession) -> dict:
    """D-01: отрасль IT, две специализации, два грейда; роли и навыки."""
    industry = await _get_or_create(session, Industry, code="it", name="Информационные технологии")

    spec_backend = await _get_or_create(session, Specialization, code="python_backend", name="Python backend")
    spec_sa = await _get_or_create(session, Specialization, code="system_analysis", name="Системный анализ")

    grade_junior = await _get_or_create(session, Grade, code="junior", name="Junior", level=1)
    grade_middle = await _get_or_create(session, Grade, code="middle", name="Middle", level=2)

    roles = {
        "backend_dev": "Backend-разработчик",
        "system_analyst": "Системный аналитик",
        "fullstack_dev": "Fullstack-разработчик",
        "data_engineer": "Data-инженер",
    }
    role_objs = {}
    for code, name in roles.items():
        role_objs[code] = await _get_or_create(session, RoleRef, code=code, name=name)

    skills = {
        "python": "Python",
        "fastapi": "FastAPI",
        "sql": "SQL",
        "postgresql": "PostgreSQL",
        "sqlalchemy": "SQLAlchemy",
        "rest_api": "REST API",
        "http": "HTTP",
        "git": "Git",
        "docker": "Docker",
        "testing": "Тестирование",
        "requirements": "Анализ требований",
        "uml": "UML",
        "data_modeling": "Моделирование данных",
        "integration": "Интеграции",
        "analytics": "Аналитика",
    }
    skill_objs = {}
    for code, name in skills.items():
        skill_objs[code] = await _get_or_create(session, Skill, code=code, name=name)

    consent = await _get_or_create(
        session,
        ConsentDoc,
        code="data_processing",
        version="1.0",
        title="Согласие на обработку персональных данных",
        text=(
            "Нажимая «Зарегистрироваться», вы даёте согласие на обработку персональных данных "
            "в целях функционирования платформы обратного найма: хранение, обработку и отображение "
            "указанных вами сведений в рамках выбранной роли. Согласие можно отозвать в любой момент. "
            "Демонстрационные данные не являются подтверждением реальной квалификации."
        ),
    )

    await session.commit()
    return {
        "industry": industry,
        "specializations": {"backend": spec_backend, "sa": spec_sa},
        "grades": {"junior": grade_junior, "middle": grade_middle},
        "roles": role_objs,
        "skills": skill_objs,
        "consent": consent,
    }


async def seed_demo_accounts(session: AsyncSession, refs: dict) -> None:
    """Демо-аккаунты обеих ролей с подтверждённым email (для локальной разработки)."""

    async def make_active_account(email: str, role: Role) -> Account | None:
        existing = await session.scalar(select(Account).where(Account.email_normalized == email))
        if existing is not None:
            return existing
        account = Account(
            email=email,
            email_normalized=email,
            password_hash=hash_password(DEMO_PASSWORD),
            role=role,
            status=AccountStatus.ACTIVE,
            consent_version=refs["consent"].version,
            consent_granted_at=datetime.now(UTC),
            confirmed_at=datetime.now(UTC),
        )
        session.add(account)
        return account

    cand = await make_active_account("candidate@example.com", Role.CANDIDATE)
    emp = await make_active_account("employer@example.com", Role.EMPLOYER)

    if cand is not None:
        await session.flush()
        profile = await session.scalar(select(CandidateProfile).where(CandidateProfile.account_id == cand.id))
        if profile is None:
            profile = CandidateProfile(
                account_id=cand.id,
                full_name="Анна Демо",
                phone="+7 900 000-00-00",
                experience_months=18,
                claimed_level_id=refs["grades"]["junior"].id,
                soft_skills=["Коммуникабельность", "Самостоятельность"],
                about="Демонстрационный профиль кандидата. Подтверждённая категория появится после прохождения теста.",
                is_published=True,
                show_fsp=False,
            )
            profile.skills = [refs["skills"]["python"], refs["skills"]["fastapi"], refs["skills"]["sql"]]
            profile.roles = [refs["roles"]["backend_dev"]]
            session.add(profile)

    if emp is not None:
        await session.flush()
        company = await session.scalar(select(Company).where(Company.account_id == emp.id))
        if company is None:
            company = Company(
                account_id=emp.id,
                name="Демо-компания ООО",
                industry_id=refs["industry"].id,
                description="Демонстрационная компания для проверки сценария работодателя.",
                contact_email=emp.email,
                website="https://example.local",
            )
            session.add(company)

    await session.commit()


async def main() -> None:
    async with async_session_factory() as session:
        refs = await seed_references(session)
        await seed_demo_accounts(session, refs)
        logger.info("Seed завершён. Демо-доступы: candidate@example.com / employer@example.com (пароль %s)", DEMO_PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())