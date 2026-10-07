"""PDF-профиль кандидата (FR-06) с проверкой прав доступа к контактам (FR-27)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_roles
from app.core import errors
from app.db.base import get_db
from app.models.account import Account, Role
from app.models.assessment import ConfirmedCategory, TestAttempt, TestAttemptStatus
from app.models.candidate import CandidateProfile
from app.models.employer import Company
from app.models.invitation import Invitation
from app.services import contacts as contacts_service
from app.services import fsp as fsp_service
from app.services import pdf as pdf_service

router = APIRouter(tags=["pdf"])

CandidateDep = Depends(require_roles(Role.CANDIDATE))
EmployerDep = Depends(require_roles(Role.EMPLOYER))


def _pdf_response(data: bytes) -> StreamingResponse:
    return StreamingResponse(
        iter([data]),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="profile.pdf"'},
    )


@router.get("/candidate/profile/pdf")
async def own_profile_pdf(
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Собственный PDF-профиль кандидата (контакты включены)."""
    profile = await db.scalar(select(CandidateProfile).where(CandidateProfile.account_id == account.id))
    if profile is None:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Сначала заполните профиль", recovery="correct_input")
    return await _render(db, profile, include_contacts=True)


@router.get("/employer/invitations/{inv_id}/profile-pdf")
async def invitation_profile_pdf(
    inv_id: uuid.UUID,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """PDF профиля для работодателя: контакты только при открытом доступе (FR-27)."""
    company = await db.scalar(select(Company).where(Company.account_id == account.id))
    inv = await db.scalar(
        select(Invitation)
        .where(Invitation.id == inv_id)
        .options(selectinload(Invitation.candidate).selectinload(CandidateProfile.account))
    )
    if inv is None or company is None or inv.company_id != company.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Приглашение не найдено", recovery="none")
    contacts_service.require_contacts(inv)
    return await _render(db, inv.candidate, include_contacts=True)


async def _render(
    db: AsyncSession,
    profile: CandidateProfile,
    *,
    include_contacts: bool,
) -> StreamingResponse:
    category = await db.scalar(
        select(ConfirmedCategory).where(
            ConfirmedCategory.candidate_id == profile.id, ConfirmedCategory.is_active.is_(True)
        )
    )
    attempts = list(
        (
            await db.scalars(
                select(TestAttempt)
                .where(
                    TestAttempt.candidate_id == profile.id,
                    TestAttempt.status == TestAttemptStatus.COMPLETED,
                )
                .order_by(TestAttempt.submitted_at.desc())
                .limit(5)
            )
        ).all()
    )

    achievements: list[str] = []
    if profile.show_fsp:
        provider = fsp_service.get_fsp_provider()
        achievements = [a.title for a in await provider.get_achievements(profile.fsp_member_id)]

    data = pdf_service.build_profile_pdf(
        profile, category, attempts, include_contacts=include_contacts, fsp_achievements=achievements
    )
    return _pdf_response(data)