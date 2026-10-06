"""Эндпоинт подбора кандидатов под потребность (FR-18..FR-22).

Карточка кандидата не содержит контактов: они открываются только после
принятия приглашения (FR-26, FR-27).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core import errors
from app.db.base import get_db
from app.models.account import Account, Role
from app.models.employer import Company, EmployerNeed
from app.schemas.matching import MatchCandidateOut
from app.services import matching as matching_service

router = APIRouter(tags=["matching"])

EmployerDep = Depends(require_roles(Role.EMPLOYER))


async def _own_need(db: AsyncSession, account: Account, need_id: uuid.UUID) -> EmployerNeed:
    company = await db.scalar(select(Company).where(Company.account_id == account.id))
    need = await db.get(EmployerNeed, need_id)
    if need is None or company is None or need.company_id != company.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS, "Потребность не найдена", recovery="none")
    return need


@router.get("/employer/needs/{need_id}/matches", response_model=list[MatchCandidateOut])
async def need_matches(
    need_id: uuid.UUID,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> list[MatchCandidateOut]:
    """Ранжированная подборка опубликованных кандидатов с подтверждённой категорией."""
    need = await _own_need(db, account, need_id)
    matches = await matching_service.match_candidates_for_need(db, need)
    return [MatchCandidateOut(**m.__dict__) for m in matches]