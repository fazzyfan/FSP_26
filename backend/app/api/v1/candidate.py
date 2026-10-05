"""Эндпоинты профиля кандидата (FR-05) с проверкой владельца (FR-03, NFR-01)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_account, require_csrf, require_roles
from app.core import errors
from app.db.base import get_db
from app.models.account import Account, Role
from app.models.candidate import CandidateProfile
from app.models.reference import Grade, RoleRef, Skill
from app.schemas.profile import CandidateProfileIn, CandidateProfileOut

router = APIRouter(prefix="/candidate", tags=["candidate"])

CandidateDep = Depends(require_roles(Role.CANDIDATE))


def _to_out(profile: CandidateProfile, account: Account) -> CandidateProfileOut:
    return CandidateProfileOut(
        full_name=profile.full_name,
        phone=profile.phone,
        contact_email=account.email,
        experience_months=profile.experience_months,
        claimed_level=profile.claimed_level.name if profile.claimed_level else None,
        claimed_level_code=profile.claimed_level.code if profile.claimed_level else None,
        roles=[r.name for r in profile.roles],
        skills=[s.name for s in profile.skills],
        soft_skills=profile.soft_skills,
        about=profile.about,
        is_published=profile.is_published,
        show_fsp=profile.show_fsp,
        fsp_member_id=profile.fsp_member_id,
        version=profile.version,
        updated_at=profile.updated_at.isoformat() if profile.updated_at else None,
    )


async def _get_own_profile(db: AsyncSession, account: Account) -> CandidateProfile | None:
    return await db.scalar(select(CandidateProfile).where(CandidateProfile.account_id == account.id))


@router.get("/profile", response_model=CandidateProfileOut | None)
async def get_profile(
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> CandidateProfileOut | None:
    """Собственный профиль (полная проекция доступна только владельцу)."""
    profile = await _get_own_profile(db, account)
    if profile is None:
        return None
    return _to_out(profile, account)


@router.put("/profile", response_model=CandidateProfileOut, dependencies=[Depends(require_csrf)])
async def upsert_profile(
    payload: CandidateProfileIn,
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> CandidateProfileOut:
    """Создание/редактирование профиля (FR-05). Заявленные навыки не становятся подтверждёнными.

    ER-05: версия записи; запоздалое сохранение из старой вкладки отклоняется (409 VERSION_CONFLICT).
    """
    profile = await _get_own_profile(db, account)
    if profile is None:
        profile = CandidateProfile(account_id=account.id)
        db.add(profile)

    # E04 REFERENCE_INVALID: справочные ID обязаны существовать
    role_ids = set(payload.role_ids)
    skill_ids = set(payload.skill_ids)
    found_roles = set((await db.scalars(select(RoleRef.id).where(RoleRef.id.in_(role_ids)))).all())
    found_skills = set((await db.scalars(select(Skill.id).where(Skill.id.in_(skill_ids)))).all())
    if len(found_roles) != len(role_ids):
        raise errors.Problem(422, errors.VALIDATION_FAILED, errors.E04_REFERENCE, "Неизвестная роль",
                             errors=[{"field": "role_ids", "code": "REFERENCE_INVALID", "error_class": "E04", "message": "Одна из ролей отсутствует в справочнике"}],
                             recovery="correct_input")
    if len(found_skills) != len(skill_ids):
        raise errors.Problem(422, errors.VALIDATION_FAILED, errors.E04_REFERENCE, "Неизвестный навык",
                             errors=[{"field": "skill_ids", "code": "REFERENCE_INVALID", "error_class": "E04", "message": "Один из навыков отсутствует в справочнике"}],
                             recovery="correct_input")
    if payload.claimed_level_id is not None:
        level = await db.get(Grade, payload.claimed_level_id)
        if level is None:
            raise errors.Problem(422, errors.VALIDATION_FAILED, errors.E04_REFERENCE, "Неизвестный уровень",
                                 errors=[{"field": "claimed_level_id", "code": "REFERENCE_INVALID", "error_class": "E04", "message": "Уровень отсутствует в справочнике"}],
                                 recovery="correct_input")

    if profile.version != payload.version:
        raise errors.Problem(409, "VERSION_CONFLICT", errors.E11_CONCURRENCY, "Профиль изменён в другой вкладке",
                             detail="Обновите страницу и повторите сохранение.", recovery="refresh")

    profile.full_name = payload.full_name
    profile.phone = payload.phone
    profile.experience_months = payload.experience_months
    profile.claimed_level_id = payload.claimed_level_id
    profile.soft_skills = payload.soft_skills
    profile.about = payload.about
    profile.is_published = payload.is_published
    profile.show_fsp = payload.show_fsp
    profile.fsp_member_id = payload.fsp_member_id
    profile.version += 1
    profile.skills = [s for s in (await db.scalars(select(Skill).where(Skill.id.in_(skill_ids)))).all()]
    profile.roles = [r for r in (await db.scalars(select(RoleRef).where(RoleRef.id.in_(role_ids)))).all()]

    await db.commit()
    await db.refresh(profile)
    return _to_out(profile, account)