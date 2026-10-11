"""Подбор кандидатов под потребность (FR-18..FR-21): ранжирование с объяснением.

Формула балла (объяснимость — FR-21):
- 60% — подтверждённые компетенции: средняя успешность блоков попытки, которая
  подтвердила категорию (не заявленные кандидатом навыки);
- 30% — результат теста: балл подтверждающей попытки (только успешной и по
  категории кандидата, а не «последней любой»);
- 10% — достижения ФСП: профиль виден в ФСП, номер участника указан и реестр
  ФСП возвращает хотя бы одно подтверждённое достижение.

Неподходящие специализации и грейды исключаются из выдачи (FR-18).
Кандидаты с деактивированным аккаунтом (отзыв обработки данных) исключаются.
Контакты не включаются: они открываются только после принятия приглашения (FR-26/27).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.account import Account, AccountStatus
from app.models.assessment import ConfirmedCategory, TestAttempt, TestAttemptStatus
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerNeed
from app.models.invitation import Invitation, InvitationStatus
from app.models.reference import Grade
from app.services import fsp as fsp_service

COMPETENCY_WEIGHT = 60
TEST_WEIGHT = 30
FSP_WEIGHT = 10

BLOCKS = (1, 2, 3)

# Явная связь «компетенция (навык) потребности → блок теста» (UPD 4, п.4):
# 60% подбора считаются по блокам, которые проверяют нужные вакансии навыки,
# а не по среднему всех блоков (которое дублировало общий результат теста).
SKILL_BLOCK_MAP: dict[str, int] = {
    "python": 1, "fastapi": 1, "sql": 1, "postgresql": 1, "sqlalchemy": 1,
    "rest_api": 2, "http": 2, "git": 2, "docker": 2, "testing": 2,
    "requirements": 3, "uml": 3, "data_modeling": 3, "integration": 3, "analytics": 3,
}


def _blocks_for_need(need: EmployerNeed) -> set[int]:
    """Блоки теста, проверяющие навыки потребности; без навыков — все блоки."""
    blocks = {SKILL_BLOCK_MAP[s.code] for s in need.skills if s.code in SKILL_BLOCK_MAP}
    return blocks or set(BLOCKS)


@dataclass
class MatchCandidate:
    candidate_id: uuid.UUID
    full_name: str
    specialization_name: str
    grade_code: str
    grade_name: str
    experience_months: int
    about: str | None = None
    skills: list[str] = field(default_factory=list)
    test_passed: bool = False
    score: int = 0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    matched_skills: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _block_success_rate(attempt: TestAttempt, blocks: set[int] | None = None) -> float:
    """Средняя успешность выбранных блоков подтверждающей попытки (60%, FR-19)."""
    blocks = blocks or set(BLOCKS)
    total_per_block = attempt.total_count // 3 if attempt.total_count else 2
    corrects = {1: attempt.block1_correct, 2: attempt.block2_correct, 3: attempt.block3_correct}
    ratios = []
    for b in BLOCKS:
        if b in blocks and total_per_block > 0:
            ratios.append(corrects[b] / total_per_block)
    return sum(ratios) / len(ratios) if ratios else 0.0


async def match_candidates_for_need(
    db: AsyncSession,
    need: EmployerNeed,
    *,
    grade_code: str | None = None,
    min_score: int = 0,
) -> list[MatchCandidate]:
    """Все опубликованные кандидаты с активным аккаунтом (FR-18..FR-21).

    Подтверждённая категория не обязательна: кандидаты без неё показываются
    с меткой «тест не пройден» и баллом 0 (работодатель видит резюме всех).
    Фильтр grade_code применяется только к кандидатам с подтверждённой
    категорией; кандидаты с неактивным аккаунтом исключаются (FR-04).
    """
    need_grade_ids = {g.id for g in need.grades}
    # Фильтр по грейду работает по всему справочнику, а не только по грейдам потребности.
    grade_by_code = {g.code: g.id for g in (await db.scalars(select(Grade))).all()}

    stmt = (
        select(CandidateProfile, ConfirmedCategory)
        .outerjoin(
            ConfirmedCategory,
            (ConfirmedCategory.candidate_id == CandidateProfile.id)
            & (ConfirmedCategory.is_active.is_(True)),
        )
        .join(Account, Account.id == CandidateProfile.account_id)
        .options(selectinload(CandidateProfile.skills))
        .where(
            CandidateProfile.is_published.is_(True),
            Account.status == AccountStatus.ACTIVE,
            # Кандидаты, уже принявшие приглашение этой компании, из подбора
            # исключаются: повторное приглашение им недоступно (одно открытое
            # приглашение на пару company+candidate, FR-23).
            ~exists().where(
                Invitation.company_id == need.company_id,
                Invitation.candidate_id == CandidateProfile.id,
                Invitation.status == InvitationStatus.ACCEPTED,
            ),
        )
    )
    if grade_code is not None:
        gid = grade_by_code.get(grade_code)
        if gid is None:
            return []
        stmt = stmt.where(ConfirmedCategory.grade_id == gid)

    rows = (await db.execute(stmt)).all()
    pairs = [(row[1], row[0]) for row in rows]
    if not pairs:
        return []

    # Подтверждающие попытки: только успешные и именно по активной категории.
    attempt_ids = {
        c.source_attempt_id for c, _ in pairs
        if c is not None and c.source_attempt_id is not None
    }
    confirming: dict[uuid.UUID, TestAttempt] = {}
    if attempt_ids:
        confirming = {
            a.id: a
            for a in (
                await db.scalars(
                    select(TestAttempt).where(
                        TestAttempt.id.in_(attempt_ids),
                        TestAttempt.status == TestAttemptStatus.COMPLETED,
                        TestAttempt.result_grade_id.isnot(None),
                    )
                )
            ).all()
        }

    fsp_provider = fsp_service.get_fsp_provider()

    results: list[MatchCandidate] = []
    for category, profile in pairs:
        if category is None:
            # Кандидат без подтверждённой категории: тест не пройден (FR-13).
            results.append(
                MatchCandidate(
                    candidate_id=profile.id,
                    full_name=profile.public_name or profile.full_name,
                    specialization_name="",
                    grade_code="",
                    grade_name="",
                    experience_months=profile.experience_months,
                    about=profile.about,
                    skills=[s.name for s in profile.skills],
                    test_passed=False,
                    score=0,
                    score_breakdown={"competencies": 0.0, "test": 0.0, "fsp": 0.0},
                    matched_skills=[],
                    reasons=["Тест не пройден — у кандидата нет подтверждённой категории."],
                )
            )
            continue

        reasons: list[str] = []
        spec_ok = need.specialization_id is None or category.specialization_id == need.specialization_id
        grade_ok = not need_grade_ids or category.grade_id in need_grade_ids
        if spec_ok:
            reasons.append(f"Специализация «{category.specialization.name}» соответствует потребности")
        else:
            reasons.append(f"Специализация «{category.specialization.name}» не совпадает с потребностью")
        if grade_ok:
            reasons.append(f"Грейд «{category.grade.name}» в допустимом диапазоне потребности")
        elif need_grade_ids:
            reasons.append(f"Грейд «{category.grade.name}» вне диапазона потребности")

        # --- 60%: компетенции, нужные вакансии (навыки потребности → блоки теста) ---
        attempt = confirming.get(category.source_attempt_id) if category.source_attempt_id else None
        if attempt is not None:
            relevant_blocks = _blocks_for_need(need)
            block_rate = _block_success_rate(attempt, relevant_blocks)
            competency_points = round(COMPETENCY_WEIGHT * block_rate, 1)
            if relevant_blocks == set(BLOCKS):
                reasons.append(
                    f"Компетенции: навыки вакансии не заданы — учтены все блоки, "
                    f"успешность {int(block_rate * 100)}% "
                    f"({competency_points} из {COMPETENCY_WEIGHT} баллов)"
                )
            else:
                skills_text = ", ".join(s.name for s in need.skills)
                reasons.append(
                    f"Компетенции вакансии ({skills_text}) → блоки "
                    f"{', '.join(str(b) for b in sorted(relevant_blocks))}: "
                    f"успешность {int(block_rate * 100)}% "
                    f"({competency_points} из {COMPETENCY_WEIGHT} баллов)"
                )
        else:
            competency_points = 0.0
            reasons.append("Компетенции не учитываются (нет подтверждающей попытки)")

        # --- 30%: результат теста (подтверждающая попытка) ---
        test_ratio = ((attempt.score_percent or 0) / 100) if attempt is not None else 0.0
        test_points = round(TEST_WEIGHT * test_ratio, 1)
        if attempt is not None:
            reasons.append(
                f"Результат теста: {attempt.score_percent}% ({test_points} из {TEST_WEIGHT} баллов)"
            )
        else:
            reasons.append("Результат теста не учитывается (нет подтверждающей попытки)")

        # --- 10%: достижения ФСП (реестр, а не просто непустой ID) ---
        fsp_points = 0.0
        if profile.show_fsp and profile.fsp_member_id:
            achievements = await fsp_provider.get_achievements(profile.fsp_member_id)
            if any(a.verified for a in achievements):
                fsp_points = FSP_WEIGHT
        if fsp_points > 0:
            reasons.append(f"Достижения ФСП подтверждены реестром ({FSP_WEIGHT} из {FSP_WEIGHT} баллов)")
        else:
            reasons.append("Достижения ФСП не подтверждены (0 баллов)")

        score = round(competency_points + test_points + fsp_points)

        if min_score > 0 and score < min_score:
            continue

        results.append(
            MatchCandidate(
                candidate_id=profile.id,
                # До согласия на контакты работодатель видит публичное имя (FR-27)
                full_name=profile.public_name or profile.full_name,
                specialization_name=category.specialization.name,
                grade_code=category.grade.code,
                grade_name=category.grade.name,
                experience_months=profile.experience_months,
                about=profile.about,
                skills=[s.name for s in profile.skills],
                test_passed=attempt is not None,
                score=score,
                score_breakdown={
                    "competencies": competency_points,
                    "test": test_points,
                    "fsp": fsp_points,
                },
                matched_skills=[],
                reasons=reasons,
            )
        )

    # Прошедшие тест — по баллу; непрошедшие (балл 0) — в конце.
    results.sort(key=lambda m: (m.score, m.experience_months), reverse=True)
    return results