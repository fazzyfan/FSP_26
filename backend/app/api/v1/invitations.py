"""Приглашения и открытие контактов (FR-23..FR-27).

Правила MVP:
- приглашение обязано содержать описание, зарплатную вилку (salary_from > 0);
  исходные условия фиксируются в строке и не изменяются;
- от одной компании кандидату одно «открытое» приглашение; повторы и
  одновременные запросы не создают дублей (идемпотентный ответ существующим);
- контакты кандидата открываются конкретной компании только после явного
  согласия кандидата; доступ можно отозвать; повтор старого принятия
  не восстанавливает доступ.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_csrf, require_roles
from app.core import errors
from app.db.base import get_db
from app.models.account import Account, Role
from app.models.assessment import ConfirmedCategory
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerNeed
from app.models.invitation import Invitation, InvitationStatus, OPEN_STATUSES
from app.schemas.invitation import (
    CandidateContactsOut,
    CandidateInvitationOut,
    EmployerInvitationOut,
    InvitationCreateIn,
    RespondIn,
)
from app.services import contacts as contacts_service

router = APIRouter(tags=["invitations"])

EmployerDep = Depends(require_roles(Role.EMPLOYER))
CandidateDep = Depends(require_roles(Role.CANDIDATE))


# ---------------------------------------------------------------- employer ---

def _inv_with_account(stmt):
    """Eager-load кандидата и его аккаунта: проверка статуса без ленивых запросов."""
    return stmt.options(selectinload(Invitation.candidate).selectinload(CandidateProfile.account))


def _employer_out(inv: Invitation, profile: CandidateProfile | None = None) -> EmployerInvitationOut:
    # После отзыва обработки данных (деактивация) ФИО кандидата не выдаётся
    prof = profile if profile is not None else inv.candidate
    account = getattr(prof, "account", None) if prof is not None else None
    visible_name = ""
    if prof is not None and account is not None and account.status.value == "active":
        visible_name = prof.full_name
    return EmployerInvitationOut(
        id=str(inv.id),
        need_id=str(inv.need_id),
        need_title=inv.need.title if inv.need else "",
        candidate_id=str(inv.candidate_id),
        candidate_name=visible_name,
        salary_from=inv.salary_from,
        salary_to=inv.salary_to,
        message=inv.message,
        status=inv.status.value,
        created_at=inv.created_at.isoformat(),
        responded_at=inv.responded_at.isoformat() if inv.responded_at else None,
        contacts_consented_at=inv.contacts_consented_at.isoformat() if inv.contacts_consented_at else None,
        contacts_revoked_at=inv.contacts_revoked_at.isoformat() if inv.contacts_revoked_at else None,
    )


async def _own_company(db: AsyncSession, account: Account) -> Company | None:
    return await db.scalar(select(Company).where(Company.account_id == account.id))


async def _open_invitation(
    db: AsyncSession, company_id: uuid.UUID, candidate_id: uuid.UUID
) -> Invitation | None:
    """Открытое приглашение компании кандидату (единственное).

    Принятое приглашение с отозванными контактами открытым не считается:
    после отзыва доступа новое предложение той же компании не блокируется.
    """
    return await db.scalar(
        _inv_with_account(
            select(Invitation).where(
                Invitation.company_id == company_id,
                Invitation.candidate_id == candidate_id,
                Invitation.status.in_(OPEN_STATUSES),
                Invitation.contacts_revoked_at.is_(None),
            )
        )
    )


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
            _inv_with_account(
                select(Invitation)
                .where(Invitation.company_id == company.id)
                .order_by(Invitation.created_at.desc())
            )
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
    response: Response,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> EmployerInvitationOut:
    """FR-23: приглашение с описанием и зарплатной вилкой.

    Идемпотентность: повторный запрос с теми же условиями возвращает
    существующее открытое приглашение (HTTP 200), дубликаты не создаются
    (в том числе при одновременных запросах — partial unique index + retry).
    """
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

    # Одно открытое приглашение от компании кандидату (FR-23, NFR-06)
    existing = await _open_invitation(db, company.id, candidate.id)
    if existing is not None:
        same_terms = (
            existing.salary_from == payload.salary_from
            and existing.salary_to == payload.salary_to
            and existing.message == payload.message
        )
        if same_terms:
            response.status_code = 200  # безопасный повтор после потери связи
            return _employer_out(existing)
        raise errors.Problem(
            409, errors.CONFLICT, errors.E11_CONCURRENCY,
            "У этой компании уже есть открытое приглашение кандидату",
            detail="Отменить текущее или дождаться ответа кандидата.", recovery="none",
        )

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
    try:
        await db.commit()
    except IntegrityError:
        # Гонка: параллельный запрос уже создал открытое приглашение.
        # Идемпотентный ответ (200) допустим только при совпадении условий —
        # иначе 409: разные условия не должны «растворяться» в существующем.
        await db.rollback()
        existing = await _open_invitation(db, company.id, candidate.id)
        if existing is None:
            raise errors.Problem(409, errors.CONFLICT, errors.E11_CONCURRENCY,
                                 "Не удалось создать приглашение, повторите запрос", recovery="retry")
        same_terms = (
            existing.salary_from == payload.salary_from
            and existing.salary_to == payload.salary_to
            and existing.message == payload.message
        )
        if not same_terms:
            raise errors.Problem(
                409, errors.CONFLICT, errors.E11_CONCURRENCY,
                "У этой компании уже есть открытое приглашение кандидату",
                detail="Параллельный запрос создал приглашение с другими условиями.",
                recovery="none",
            )
        response.status_code = 200
        return _employer_out(existing)
    await db.refresh(invitation)
    # Вновь созданная строка ещё не несёт кандидата — передаём уже загруженный профиль
    return _employer_out(invitation, profile=candidate)


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
    inv = await db.scalar(_inv_with_account(select(Invitation).where(Invitation.id == inv_id)))
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
    """FR-27: контакты открываются только после принятия и согласия кандидата.

    Отзыв доступа закрывает контакты; повторное принятие их не восстанавливает.
    """
    company = await _own_company(db, account)
    inv = await db.scalar(
        select(Invitation)
        .where(Invitation.id == inv_id)
        .options(selectinload(Invitation.candidate).selectinload(CandidateProfile.account))
    )
    if inv is None or company is None or inv.company_id != company.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Приглашение не найдено", recovery="none")
    contacts_service.require_contacts(inv)

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
        company_contact_email=inv.company.contact_email if inv.company else None,
        company_phone=inv.company.phone if inv.company else None,
        contacts_consented_at=inv.contacts_consented_at.isoformat() if inv.contacts_consented_at else None,
        contacts_revoked_at=inv.contacts_revoked_at.isoformat() if inv.contacts_revoked_at else None,
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
    """FR-25: принятие или отклонение. Принятие = явное согласие открыть контакты.

    Повторный accept (после потери связи) идемпотентен: статус и согласие не
    меняются, отозванный доступ не восстанавливается.
    """
    profile = await _own_profile(db, account)
    # Блокируем строку по id (FOR UPDATE на joined-связи запрещён в Postgres),
    # затем загружаем приглашение в этой же транзакции — конкурирующие запросы
    # к той же строке ждут фиксации первой (атомарный respond).
    locked = await db.scalar(select(Invitation.id).where(Invitation.id == inv_id).with_for_update())
    if locked is None:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Приглашение не найдено", recovery="none")
    inv = await db.get(Invitation, inv_id)
    if inv is None or inv.candidate_id != profile.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Приглашение не найдено", recovery="none")

    if inv.status == InvitationStatus.ACCEPTED:
        if payload.decision == "accept":
            # Идемпотентный повтор старого принятия; контакты не переоткрываются
            return _candidate_out(inv)
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Приглашение уже принято", recovery="none")

    if inv.status != InvitationStatus.PENDING:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Приглашение уже обработано", recovery="none")

    inv.status = InvitationStatus.ACCEPTED if payload.decision == "accept" else InvitationStatus.DECLINED
    inv.responded_at = datetime.now(UTC)
    if payload.decision == "accept":
        # Явное согласие кандидата на открытие контактов именно этой компании (FR-27)
        inv.contacts_consented_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(inv)
    return _candidate_out(inv)


@router.post(
    "/candidate/invitations/{inv_id}/contacts/revoke",
    response_model=CandidateInvitationOut,
    dependencies=[Depends(require_csrf)],
)
async def revoke_contacts(
    inv_id: uuid.UUID,
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> CandidateInvitationOut:
    """Отзыв доступа к контактам (FR-27). Контакты закрываются немедленно;
    повторное принятие приглашения доступ не восстанавливает.

    Атомарность: строка блокируется — одновременные отзывы не дают двойного
    «успеха» и не рассинхронизируют уникальный индекс открытых приглашений.
    """
    profile = await _own_profile(db, account)
    locked = await db.scalar(select(Invitation.id).where(Invitation.id == inv_id).with_for_update())
    if locked is None:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Приглашение не найдено", recovery="none")
    inv = await db.get(Invitation, inv_id)
    if inv is None or inv.candidate_id != profile.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Приглашение не найдено", recovery="none")
    if inv.status != InvitationStatus.ACCEPTED or inv.contacts_consented_at is None:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Контакты по этому приглашению не открыты", recovery="none")
    if inv.contacts_revoked_at is not None:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Доступ уже отозван", recovery="none")
    inv.contacts_revoked_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(inv)
    return _candidate_out(inv)