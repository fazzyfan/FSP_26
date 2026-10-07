"""Эндпоинт подбора кандидатов под потребность (FR-18..FR-22).

Карточка кандидата не содержит контактов: они открываются только после
принятия приглашения (FR-26, FR-27). Поддерживаются фильтры по грейду и
минимальному баллу, а также пагинация.
"""

from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core import errors
from app.db.base import get_db
from app.models.account import Account, Role
from app.models.employer import Company, EmployerNeed
from app.schemas.matching import MatchCandidateOut, MatchPageOut
from app.services import matching as matching_service

router = APIRouter(tags=["matching"])

EmployerDep = Depends(require_roles(Role.EMPLOYER))

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50


async def _own_need(db: AsyncSession, account: Account, need_id: uuid.UUID) -> EmployerNeed:
    company = await db.scalar(select(Company).where(Company.account_id == account.id))
    need = await db.get(EmployerNeed, need_id)
    if need is None or company is None or need.company_id != company.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS, "Потребность не найдена", recovery="none")
    return need


@router.get("/employer/needs/{need_id}/matches", response_model=MatchPageOut)
async def need_matches(
    need_id: uuid.UUID,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1, description="Номер страницы"),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Размер страницы"),
    grade: str | None = Query(default=None, description="Фильтр по коду грейда"),
    min_score: int = Query(default=0, ge=0, le=100, description="Минимальный балл подбора"),
) -> MatchPageOut:
    """Ранжированная подборка опубликованных кандидатов с подтверждённой категорией.

    Балл: 60% компетенции + 30% тест + 10% достижения ФСП. Неподходящие
    специализации и грейды исключаются.
    """
    need = await _own_need(db, account, need_id)
    matches = await matching_service.match_candidates_for_need(
        db, need, grade_code=grade, min_score=min_score
    )

    total = len(matches)
    pages = max(1, math.ceil(total / page_size)) if total else 0
    start = (page - 1) * page_size
    slice_items = matches[start : start + page_size]

    return MatchPageOut(
        items=[MatchCandidateOut(**m.__dict__) for m in slice_items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )