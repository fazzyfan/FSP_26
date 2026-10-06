"""Приглашения и открытие контактов (FR-23..FR-27).

Контакты кандидата доступны работодателю только после принятия приглашения (FR-27).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_csrf, require_roles
from app.core import errors
from app.db.base import get_db
from app.models.account import Account, Role
from app.models.assessment import ConfirmedCategory
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerNeed
from app.models.invitation import Invitation, InvitationStatus
from app.schemas.invitation import (
    CandidateContactsOut,
    CandidateInvitationOut,
    EmployerInvitationOut,
    InvitationCreateIn,
    RespondIn,
)

router = APIRouter(tags=["invitations"])

EmployerDep = Depends(require_roles(Role.EMPLOYER))
CandidateDep = Depends(require_roles(Role.CANDIDATE))


# ---------------------------------------------------------------- employer ---

def _employer_out(inv: Invitation) -> EmployerInvitationOut:
    return EmployerInvitationOut(
        id=str(inv.id),
        need_id=str(inv.need_id),
        need_title=inv.need.title if inv.need else "",
        candidate_id=str(inv.candidate_id),
        candidate_name=inv.candidate.full_name if inv.candidate else "",
        salary_from=inv.salary_from,
        salary_to=inv.salary_to,
        message=inv.message,
        status=inv.status.value,
        created_at=inv.created_at.isoformat(),
        responded_at=inv.responded_at.isoformat() if inv.responded_at else None,
    )


async def _own_company(db: AsyncSession, account: Account) -> Company | None:
    return await db.scalar(select(Company).where(Company.account_id == account.id))


@router.get("/employer/invitations", response_model=list[EmployerInvitationOut])
async def employer_list_invitations(
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> list[EmployerInvitationOut]:
    company = await _own_company(db, account)
    if company is None:
        return []
    invites = (
        await db.scalars(
            select(Invitation)
            .where(Invitation.company_id == company.id)
            .order_by(Invitation.created_at.desc())
        )
    ).all()
    return [_employer_out(i) for i in invites]


@router.post(
    "/employer/needs/{need_id}/invitations",
    response_model=EmployerInvitationOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_invitation(
    need_id: uuid.UUID,
    payload: InvitationCreateIn,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> EmployerInvitationOut:
    """FR-23: приглашение с зарплатной вилкой. Только опубликованным кандидатам с категорией."""
    company = await _own_company(db, account)
    if company is None:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Сначала заполните профиль компании", recovery="correct_input")
    need = await db.get(EmployerNeed, need_id)
    if need is None or need.company_id != company.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Потребность не найдена", recovery="none")

    candidate = await db.get(CandidateProfile, payload.candidate_id)
    if candidate is None or not candidate.is_published:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Кандидат не найден или скрыл профиль", recovery="none")
    category = await db.scalar(
        select(ConfirmedCategory).where(
            ConfirmedCategory.candidate_id == candidate.id, ConfirmedCategory.is_active.is_(True)
        )
    )
    if category is None:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "У кандидата нет подтверждённой категории",
                             detail="Приглашать можно кандидатов, прошедших тест.", recovery="correct_input")

    duplicate = await db.scalar(
        select(Invitation).where(
            Invitation.need_id == need.id,
            Invitation.candidate_id == candidate.id,
            Invitation.status.in_([InvitationStatus.PENDING, InvitationStatus.ACCEPTED]),
        )
    )
    if duplicate is not None:
        raise errors.Problem(409, errors.CONFLICT, errors.E11_CONCURRENCY,
                             "Приглашение этому кандидату уже отправлено", recovery="none")

    invitation = Invitation(
        need_id=need.id,
        company_id=company.id,
        candidate_id=candidate.id,
        salary_from=payload.salary_from,
        salary_to=payload.salary_to,
        message=payload.message,
        status=InvitationStatus.PENDING,
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return _employer_out(invitation)


@router.post(
    "/employer/invitations/{inv_id}/withdraw",
    response_model=EmployerInvitationOut,
    dependencies=[Depends(require_csrf)],
)
async def withdraw_invitation(
    inv_id: uuid.UUID,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> EmployerInvitationOut:
    company = await _own_company(db, account)
    inv = await db.get(Invitation, inv_id)
    if inv is None or company is None or inv.company_id != company.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Приглашение не найдено", recovery="none")
    if inv.status != InvitationStatus.PENDING:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Отозвать можно только ожидающее приглашение", recovery="none")
    inv.status = InvitationStatus.WITHDRAWN
    inv.responded_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(inv)
    return _employer_out(inv)


@router.get("/employer/invitations/{inv_id}/contacts", response_model=CandidateContactsOut)
async def invitation_contacts(
    inv_id: uuid.UUID,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> CandidateContactsOut:
    """FR-27: контакты открываются только после принятия приглашения."""
    company = await _own_company(db, account)
    inv = await db.get(Invitation, inv_id)
    if inv is None or company is None or inv.company_id != company.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Приглашение не найдено", recovery="none")
    if inv.status != InvitationStatus.ACCEPTED:
        raise errors.Problem(
            409, errors.INVALID_STATE, errors.E12_STATE, "Контакты пока закрыты",
            detail="Контакты кандидата открываются после принятия приглашения.",
            recovery="none",
        )
    candidate = inv.candidate
    inv.contacts_viewed_at = datetime.now(UTC)
    await db.commit()
    return CandidateContactsOut(
        full_name=candidate.full_name,
        phone=candidate.phone,
        email=candidate.account.email if candidate.account else "",
        about=candidate.about,
    )


# --------------------------------------------------------------- candidate ---

def _candidate_out(inv: Invitation) -> CandidateInvitationOut:
    return CandidateInvitationOut(
        id=str(inv.id),
        company_id=str(inv.company_id),
        company_name=inv.company.name if inv.company else "",
        need_title=inv.need.title if inv.need else "",
        salary_from=inv.salary_from,
        salary_to=inv.salary_to,
        message=inv.message,
        status=inv.status.value,
        created_at=inv.created_at.isoformat(),
        responded_at=inv.responded_at.isoformat() if inv.responded_at else None,
    )


async def _own_profile(db: AsyncSession, account: Account) -> CandidateProfile:
    profile = await db.scalar(select(CandidateProfile).where(CandidateProfile.account_id == account.id))
    if profile is None:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Сначала заполните профиль", recovery="correct_input")
    return profile


@router.get("/candidate/invitations", response_model=list[CandidateInvitationOut])
async def candidate_list_invitations(
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> list[CandidateInvitationOut]:
    profile = await _own_profile(db, account)
    invites = (
        await db.scalars(
            select(Invitation)
            .where(Invitation.candidate_id == profile.id)
            .order_by(Invitation.created_at.desc())
        )
    ).all()
    return [_candidate_out(i) for i in invites]


@router.post(
    "/candidate/invitations/{inv_id}/respond",
    response_model=CandidateInvitationOut,
    dependencies=[Depends(require_csrf)],
)
async def respond_invitation(
    inv_id: uuid.UUID,
    payload: RespondIn,
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> CandidateInvitationOut:
    """FR-25: принятие или отклонение приглашения. Принятие открывает контакты работодателю."""
    profile = await _own_profile(db, account)
    inv = await db.get(Invitation, inv_id)
    if inv is None or inv.candidate_id != profile.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Приглашение не найдено", recovery="none")
    if inv.status != InvitationStatus.PENDING:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Приглашение уже обработано", recovery="none")
    inv.status = InvitationStatus.ACCEPTED if payload.decision == "accept" else InvitationStatus.DECLINED
    inv.responded_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(inv)
    return _candidate_out(inv)