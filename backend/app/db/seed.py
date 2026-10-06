"""Seed справочников и демонстрационных данных (FR-28).

Запуск: python -m app.db.seed
Идемпотентен: повторный запуск не создаёт дублей и не стирает пользовательские записи.
Демо-данные явно помечены как демонстрационные (FR-15, NFR-04).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import async_session_factory
from app.models.account import Account, AccountStatus, ConsentDoc, Role
from app.models.assessment import TestQuestion, TestQuestionOption
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerNeed
from app.models.reference import Grade, Industry, RoleRef, Skill, Specialization

logger = logging.getLogger("fsp.seed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

DEMO_PASSWORD = "DemoPass2026!"

# Вопросы теста: специализация -> список (grade_level, текст, [(вариант, is_correct), ...], объяснение)
TEST_QUESTIONS: dict[str, list[tuple[int, str, list[tuple[str, bool]], str | None]]] = {
    "python_backend": [
        (
            1,
            "Что такое REST API?",
            [
                ("Архитектурный стиль взаимодействия клиента и сервера по HTTP", True),
                ("Язык разметки для описания интерфейсов", False),
                ("Протокол шифрования трафика", False),
                ("Формат хранения данных в базе", False),
            ],
            "REST — набор принципов построения HTTP-интерфейсов (ресурсы, методы, статусы).",
        ),
        (
            1,
            "Какой из перечисленных типов данных в Python является неизменяемым?",
            [
                ("list", False),
                ("dict", False),
                ("tuple", True),
                ("set", False),
            ],
            "Кортеж (tuple) неизменяем; list, dict и set — изменяемые.",
        ),
        (
            1,
            "Какая команда создаёт изолированное окружение для проекта на Python?",
            [
                ("pip install -r requirements.txt", False),
                ("python -m venv .venv", True),
                ("uvicorn app.main:app", False),
                ("alembic upgrade head", False),
            ],
            "python -m venv .venv создаёт виртуальное окружение в каталоге .venv.",
        ),
        (
            2,
            "Для чего в базах данных используются индексы?",
            [
                ("Для ускорения поиска и фильтрации записей", True),
                ("Для шифрования данных", False),
                ("Для автоматического резервного копирования", False),
                ("Для ограничения числа пользователей", False),
            ],
            "Индексы ускоряют выборки за счёт дополнительной структуры поиска.",
        ),
        (
            2,
            "Чем метод PUT отличается от PATCH в HTTP?",
            [
                ("PUT обновляет ресурс целиком, PATCH — частично", True),
                ("PUT асинхронный, PATCH синхронный", False),
                ("Это синонимы", False),
                ("PATCH удаляет ресурс, PUT создаёт", False),
            ],
            "PUT заменяет представление ресурса целиком, PATCH применяет частичные изменения.",
        ),
        (
            2,
            "Как правильно выполнить несколько операций с БД атомарно?",
            [
                ("Завернуть их в одну транзакцию", True),
                ("Выполнить запросы параллельно в потоках", False),
                ("Продублировать запросы", False),
                ("Отправить их без подтверждения", False),
            ],
            "Атомарность обеспечивается единой транзакцией: либо все изменения, либо ни одного.",
        ),
    ],
    "system_analysis": [
        (
            1,
            "Что такое функциональное требование?",
            [
                ("Описание того, что система должна делать", True),
                ("Требование к скорости работы системы", False),
                ("Описание интерфейса пользователя", False),
                ("Правило резервного копирования", False),
            ],
            "Функциональное требование описывает поведение системы: что она делает.",
        ),
        (
            1,
            "Что описывает use case (вариант использования)?",
            [
                ("Сценарий взаимодействия пользователя с системой", True),
                ("Схему базы данных", False),
                ("Расписание релизов", False),
                ("Тексты интерфейса", False),
            ],
            "Use case — сценарий достижения цели пользователем через систему.",
        ),
        (
            1,
            "Какой артефакт нагляднее всего описывает структуру данных системы?",
            [
                ("ER-диаграмма (сущности и связи)", True),
                ("Диаграмма Ганта", False),
                ("Блок-схема алгоритма", False),
                ("Прототип экрана", False),
            ],
            "ER-диаграмма показывает сущности, атрибуты и связи между ними.",
        ),
        (
            2,
            "Чем модель TO-BE отличается от AS-IS?",
            [
                ("TO-BE — целевое состояние после внедрения, AS-IS — текущее", True),
                ("Это синонимы", False),
                ("AS-IS описывает будущее, TO-BE — настоящее", False),
                ("TO-BE — это диаграмма БД, AS-IS — прототип", False),
            ],
            "AS-IS фиксирует текущие процессы, TO-BE — целевые после изменений.",
        ),
        (
            2,
            "Что относится к нефункциональным требованиям?",
            [
                ("Время отклика системы не более 2 секунд", True),
                ("Пользователь может создать заказ", False),
                ("Система отправляет уведомление после оплаты", False),
                ("Администратор блокирует пользователя", False),
            ],
            "НФТ описывают качественные характеристики: производительность, безопасность и др.",
        ),
        (
            2,
            "Зачем аналитику описывать контракт REST API?",
            [
                ("Чтобы зафиксировать запросы, ответы и коды ошибок для разработки", True),
                ("Чтобы заменить документацию пользователя", False),
                ("Чтобы рассчитать стоимость серверов", False),
                ("Чтобы проверить скорость сети", False),
            ],
            "Контракт API согласует ожидания команды: методы, поля, статусы, ошибки.",
        ),
    ],
}


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
        "specializations": {"python_backend": spec_backend, "system_analysis": spec_sa},
        "grades": {"junior": grade_junior, "middle": grade_middle},
        "roles": role_objs,
        "skills": skill_objs,
        "consent": consent,
    }


async def seed_test_questions(session: AsyncSession, refs: dict) -> None:
    """FR-08/FR-09: по 6 вопросов на специализацию (3 Junior + 3 Middle)."""
    for spec_key, questions in TEST_QUESTIONS.items():
        spec = refs["specializations"][spec_key]
        existing = await session.scalar(
            select(func.count(TestQuestion.id)).where(TestQuestion.specialization_id == spec.id)
        )
        if existing:
            logger.info("Вопросы для %s уже есть (%s шт.), пропускаю", spec_key, existing)
            continue
        for idx, (grade_level, text, options, explanation) in enumerate(questions, start=1):
            question = TestQuestion(
                specialization_id=spec.id,
                grade_level=grade_level,
                text=text,
                explanation=explanation,
                is_active=True,
                sort_order=idx,
            )
            session.add(question)
            await session.flush()
            for opt_idx, (opt_text, is_correct) in enumerate(options, start=1):
                session.add(
                    TestQuestionOption(
                        question_id=question.id,
                        text=opt_text,
                        is_correct=is_correct,
                        sort_order=opt_idx,
                    )
                )
        logger.info("Добавлены вопросы теста по специализации %s", spec_key)
    await session.commit()


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
            await session.flush()

        # Демо-потребность, чтобы страница подбора сразу показывала результат (FR-17)
        demo_need = await session.scalar(
            select(EmployerNeed).where(EmployerNeed.company_id == company.id, EmployerNeed.title == "Backend-разработчик (Python)")
        )
        if demo_need is None:
            demo_need = EmployerNeed(
                company_id=company.id,
                title="Backend-разработчик (Python)",
                tasks_text=(
                    "Развивать сервис на FastAPI: проектировать модели данных, реализовывать API, "
                    "интегрироваться с внешними системами и поддерживать качество кода тестами."
                ),
                industry_id=refs["industry"].id,
                specialization_id=refs["specializations"]["python_backend"].id,
                grades=[refs["grades"]["junior"], refs["grades"]["middle"]],
                skills=[refs["skills"]["python"], refs["skills"]["fastapi"], refs["skills"]["sql"]],
            )
            session.add(demo_need)

    await session.commit()


async def main() -> None:
    async with async_session_factory() as session:
        refs = await seed_references(session)
        await seed_test_questions(session, refs)
        await seed_demo_accounts(session, refs)
        logger.info("Seed завершён. Демо-доступы: candidate@example.com / employer@example.com (пароль %s)", DEMO_PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())