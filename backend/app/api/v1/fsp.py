"""Демонстрационный адаптер ФСП (FR-14, FR-15): достижения участника."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core import errors
from app.db.base import get_db
from app.models.account import Account, Role
from app.models.candidate import CandidateProfile
from app.services import fsp as fsp_service

router = APIRouter(prefix="/candidate/fsp", tags=["fsp"])

CandidateDep = Depends(require_roles(Role.CANDIDATE))


class AchievementOut(BaseModel):
    code: str
    title: str
    description: str
    verified: bool


class FspAchievementsOut(BaseModel):
    member_id: str | None
    visible: bool
    achievements: list[AchievementOut]


@router.get("/achievements", response_model=FspAchievementsOut)
async def my_fsp_achievements(
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> FspAchievementsOut:
    """Достижения ФСП через демо-адаптер (показываются, если включён показ)."""
    profile = await db.scalar(select(CandidateProfile).where(CandidateProfile.account_id == account.id))
    if profile is None:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Сначала заполните профиль", recovery="correct_input")

    provider = fsp_service.get_fsp_provider()
    items = await provider.get_achievements(profile.fsp_member_id if profile.show_fsp else None)
    return FspAchievementsOut(
        member_id=profile.fsp_member_id,
        visible=profile.show_fsp,
        achievements=[
            AchievementOut(code=a.code, title=a.title, description=a.description, verified=a.verified)
            for a in items
        ],
    )