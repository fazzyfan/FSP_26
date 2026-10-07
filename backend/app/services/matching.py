"""Подбор кандидатов под потребность (FR-18..FR-21): ранжирование с объяснением.

Формула балла (объяснимость — FR-21):
- 60% — подтверждённые компетенции (доля навыков потребности у кандидата);
- 30% — результат теста (последняя завершённая попытка по категории);
- 10% — достижения ФСП (профиль виден в ФСП и участник подтверждён).

Неподходящие специализации и грейды исключаются из выдачи (FR-18).
Контакты не включаются: они открываются только после принятия приглашения (FR-26/27).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assessment import ConfirmedCategory, TestAttempt, TestAttemptStatus
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerNeed

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


async def match_candidates_for_need(
    db: AsyncSession,
    need: EmployerNeed,
    *,
    grade_code: str | None = None,
    min_score: int = 0,
) -> list[MatchCandidate]:
    """Опубликованные кандидаты с активной категорией, подходящей потребности.

    Исключаются кандидаты с другой специализацией и грейдом вне диапазона
    потребности (или вне выбранного фильтра grade_code).
    """
    need_grade_ids = {g.id for g in need.grades}
    grade_by_code = {g.code: g.id for g in need.grades}

    stmt = (
        select(CandidateProfile, ConfirmedCategory)
        .join(ConfirmedCategory, ConfirmedCategory.candidate_id == CandidateProfile.id)
        .options(selectinload(CandidateProfile.skills))
        .where(
            CandidateProfile.is_published.is_(True),
            ConfirmedCategory.is_active.is_(True),
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

    candidate_ids = [c.id for _, c in pairs]
    # Последняя завершённая попытка на кандидата (результат теста, 30%)
    attempts = (
        await db.scalars(
            select(TestAttempt)
            .where(
                TestAttempt.candidate_id.in_(candidate_ids),
                TestAttempt.status == TestAttemptStatus.COMPLETED,
            )
            .order_by(TestAttempt.submitted_at.desc())
        )
    ).all()
    best_by_candidate: dict[uuid.UUID, TestAttempt] = {}
    for a in attempts:
        best_by_candidate.setdefault(a.candidate_id, a)

    results: list[MatchCandidate] = []
    for category, profile in pairs:
        reasons: list[str] = []
        if need.specialization_id is not None:
            reasons.append(f"Специализация «{category.specialization.name}» соответствует потребности")

        grade_ok = not need_grade_ids or category.grade_id in need_grade_ids
        if grade_ok:
            reasons.append(f"Грейд «{category.grade.name}» в допустимом диапазоне потребности")

        # --- 60%: компетенции (навыки) ---
        need_skills = {s.id: s.name for s in need.skills}
        profile_skills = {s.id for s in profile.skills}
        matched = [name for sid, name in need_skills.items() if sid in profile_skills]
        competency_ratio = len(matched) / len(need_skills) if need_skills else 0.0
        competency_points = round(COMPETENCY_WEIGHT * competency_ratio, 1)
        if need_skills:
            reasons.append(
                f"Компетенции: {len(matched)} из {len(need_skills)} навыков "
                f"({competency_points} из {COMPETENCY_WEIGHT} баллов)"
            )

        # --- 30%: результат теста ---
        attempt = best_by_candidate.get(profile.id)
        test_ratio = (attempt.score_percent or 0) / 100 if attempt else 0.0
        test_points = round(TEST_WEIGHT * test_ratio, 1)
        if attempt is not None:
            reasons.append(f"Результат теста: {attempt.score_percent}% ({test_points} из {TEST_WEIGHT} баллов)")
        else:
            reasons.append("Результат теста не учитывается (нет завершённой попытки)")

        # --- 10%: достижения ФСП ---
        fsp_ok = bool(profile.show_fsp and profile.fsp_member_id)
        fsp_points = FSP_WEIGHT if fsp_ok else 0.0
        if fsp_ok:
            reasons.append(f"Достижения ФСП подтверждены ({FSP_WEIGHT} из {FSP_WEIGHT} баллов)")
        else:
            reasons.append("Достижения ФСП не указаны (0 баллов)")

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
                matched_skills=matched,
                reasons=reasons,
            )
        )

    results.sort(key=lambda m: (m.score, m.experience_months), reverse=True)
    return results