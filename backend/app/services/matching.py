"""Подбор кандидатов под потребность (FR-18..FR-21): ранжирование с объяснением.

Вес факторов (объяснимость — требование FR-21):
- специализация 40 баллов;
- грейд в допустимом диапазоне потребности 30 баллов;
- пересечение навыков до 30 баллов (доля от навыков потребности).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assessment import ConfirmedCategory
from app.models.candidate import CandidateProfile
from app.models.employer import EmployerNeed

SPEC_WEIGHT = 40
GRADE_WEIGHT = 30
SKILL_WEIGHT = 30


@dataclass
class MatchCandidate:
    candidate_id: uuid.UUID
    full_name: str
    specialization_name: str
    grade_code: str
    grade_name: str
    experience_months: int
    score: int
    matched_skills: list[str]
    reasons: list[str] = field(default_factory=list)


async def match_candidates_for_need(db: AsyncSession, need: EmployerNeed) -> list[MatchCandidate]:
    """Опубликованные кандидаты с активной подтверждённой категорией, ранжированные по score.

    Контакты не включаются: они открываются только после принятия приглашения (FR-26/FR-27).
    """
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

    result = await db.execute(stmt)
    rows = result.all()
    return _score_rows([(row[1], row[0]) for row in rows], need)


def _score_rows(pairs: list[tuple[ConfirmedCategory, CandidateProfile]], need: EmployerNeed) -> list[MatchCandidate]:
    need_grade_ids = {g.id for g in need.grades}
    need_skills = {s.id: s.name for s in need.skills}
    need_skill_ids = set(need_skills.keys())

    results: list[MatchCandidate] = []
    for category, profile in pairs:
        reasons: list[str] = []
        score = 0

        if need.specialization_id is None or category.specialization_id == need.specialization_id:
            score += SPEC_WEIGHT
            reasons.append(
                f"Специализация «{category.specialization.name}» соответствует потребности"
                if need.specialization_id
                else "Специализация учтена"
            )
        else:
            reasons.append("Специализация не совпадает")

        if category.grade_id in need_grade_ids:
            score += GRADE_WEIGHT
            reasons.append(f"Грейд «{category.grade.name}» в допустимом диапазоне потребности")
        else:
            reasons.append(f"Грейд «{category.grade.name}» вне диапазона потребности")

        profile_skills = {s.id: s.name for s in profile.skills}
        matched = [name for sid, name in need_skills.items() if sid in profile_skills]
        if need_skill_ids:
            score += round(SKILL_WEIGHT * len(matched) / len(need_skill_ids))
            if matched:
                reasons.append(f"Совпадают навыки ({len(matched)} из {len(need_skill_ids)}): {', '.join(matched)}")
            else:
                reasons.append("Совпадений по навыкам нет")

        results.append(
            MatchCandidate(
                candidate_id=profile.id,
                full_name=profile.full_name,
                specialization_name=category.specialization.name,
                grade_code=category.grade.code,
                grade_name=category.grade.name,
                experience_months=profile.experience_months,
                score=score,
                matched_skills=matched,
                reasons=reasons,
            )
        )

    results.sort(key=lambda m: (m.score, m.experience_months), reverse=True)
    return results