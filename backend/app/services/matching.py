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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.account import Account, AccountStatus
from app.models.assessment import ConfirmedCategory, TestAttempt, TestAttemptStatus
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerNeed
from app.services import fsp as fsp_service

COMPETENCY_WEIGHT = 60
TEST_WEIGHT = 30
FSP_WEIGHT = 10


@dataclass
class MatchCandidate:
    candidate_id: uuid.UUID
    full_name: str
    specialization_name: str
    grade_code: str
    grade_name: str
    experience_months: int
    score: int
    score_breakdown: dict[str, float]
    matched_skills: list[str]
    reasons: list[str] = field(default_factory=list)


def _block_success_rate(attempt: TestAttempt) -> float:
    """Средняя успешность блоков подтверждающей попытки (60%, FR-19)."""
    totals = [attempt.total_count // 3] * 3 if attempt.total_count else [2, 2, 2]
    corrects = [attempt.block1_correct, attempt.block2_correct, attempt.block3_correct]
    ratios = []
    for total, correct in zip(totals, corrects):
        if total > 0:
            ratios.append(correct / total)
    return sum(ratios) / len(ratios) if ratios else 0.0


async def match_candidates_for_need(
    db: AsyncSession,
    need: EmployerNeed,
    *,
    grade_code: str | None = None,
    min_score: int = 0,
) -> list[MatchCandidate]:
    """Опубликованные кандидаты с активной категорией, подходящей потребности.

    Исключаются кандидаты с другой специализацией и грейдом вне диапазона
    потребности (или вне выбранного фильтра grade_code), а также кандидаты
    с неактивным аккаунтом (отзыв обработки данных, FR-04).
    """
    need_grade_ids = {g.id for g in need.grades}
    grade_by_code = {g.code: g.id for g in need.grades}

    stmt = (
        select(CandidateProfile, ConfirmedCategory)
        .join(ConfirmedCategory, ConfirmedCategory.candidate_id == CandidateProfile.id)
        .join(Account, Account.id == CandidateProfile.account_id)
        .options(selectinload(CandidateProfile.skills))
        .where(
            CandidateProfile.is_published.is_(True),
            ConfirmedCategory.is_active.is_(True),
            Account.status == AccountStatus.ACTIVE,
        )
    )
    if need.specialization_id is not None:
        stmt = stmt.where(ConfirmedCategory.specialization_id == need.specialization_id)
    if need_grade_ids:
        stmt = stmt.where(ConfirmedCategory.grade_id.in_(need_grade_ids))
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
    # Никаких «последних попыток» другой категории или проваленных.
    attempt_ids = {c.source_attempt_id for _, c in pairs if c.source_attempt_id is not None}
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
        reasons: list[str] = []
        if need.specialization_id is not None:
            reasons.append(f"Специализация «{category.specialization.name}» соответствует потребности")

        grade_ok = not need_grade_ids or category.grade_id in need_grade_ids
        if grade_ok:
            reasons.append(f"Грейд «{category.grade.name}» в допустимом диапазоне потребности")

        # --- 60%: компетенции (подтверждённые блоки попытки, а не self-reported навыки) ---
        attempt = confirming.get(category.source_attempt_id) if category.source_attempt_id else None
        if attempt is not None:
            block_rate = _block_success_rate(attempt)
            competency_points = round(COMPETENCY_WEIGHT * block_rate, 1)
            reasons.append(
                f"Компетенции: подтверждённые блоки {attempt.score_percent}%, "
                f"успешность блоков {int(block_rate * 100)}% "
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
                full_name=profile.full_name,
                specialization_name=category.specialization.name,
                grade_code=category.grade.code,
                grade_name=category.grade.name,
                experience_months=profile.experience_months,
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

    results.sort(key=lambda m: (m.score, m.experience_months), reverse=True)
    return results