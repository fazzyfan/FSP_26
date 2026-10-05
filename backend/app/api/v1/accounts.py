"""Эндпоинты «о себе» и кабинеты-агрегаты."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_account
from app.db.base import get_db
from app.models.account import Account
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerNeed

router = APIRouter(tags=["me"])


class MeOut(BaseModel):
    id: str
    email: str
    role: str
    status: str
    has_profile: bool
    has_company: bool
    needs_count: int


@router.get("/me", response_model=MeOut)
async def me(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> MeOut:
    """Сводка для фронта: роль определяет кабинет (кандидат/работодатель)."""
    has_profile = (
        await db.scalar(select(CandidateProfile.id).where(CandidateProfile.account_id == account.id))
    ) is not None
    company = await db.scalar(select(Company).where(Company.account_id == account.id))
    needs_count = 0
    if company is not None:
        needs_count = len((await db.scalars(select(EmployerNeed).where(EmployerNeed.company_id == company.id))).all())
    return MeOut(
        id=str(account.id),
        email=account.email,
        role=account.role.value,
        status=account.status.value,
        has_profile=has_profile,
        has_company=company is not None,
        needs_count=int(needs_count),
    )