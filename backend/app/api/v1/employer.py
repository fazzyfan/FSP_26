"""Эндпоинты компании и потребностей работодателя (FR-16, FR-17)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_account, require_csrf, require_roles
from app.core import errors
from app.db.base import get_db
from app.models.account import Account, Role
from app.models.employer import Company, EmployerNeed
from app.models.reference import Grade, Industry, Skill, Specialization
from app.schemas.profile import CompanyIn, CompanyOut, EmployerNeedIn, EmployerNeedOut

router = APIRouter(prefix="/employer", tags=["employer"])

EmployerDep = Depends(require_roles(Role.EMPLOYER))


def _company_out(c: Company) -> CompanyOut:
    return CompanyOut(
        id=str(c.id),
        name=c.name,
        industry_id=str(c.industry_id) if c.industry_id else None,
        industry_name=c.industry.name if c.industry else None,
        description=c.description,
        contact_email=c.contact_email,
        website=c.website,
        phone=c.phone,
        version=c.version,
    )


def _need_out(n: EmployerNeed) -> EmployerNeedOut:
    return EmployerNeedOut(
        id=str(n.id),
        company_id=str(n.company_id),
        title=n.title,
        tasks_text=n.tasks_text,
        industry_id=str(n.industry_id) if n.industry_id else None,
        specialization_id=str(n.specialization_id) if n.specialization_id else None,
        grade_ids=[str(g.id) for g in n.grades],
        skill_ids=[str(s.id) for s in n.skills],
        created_at=n.created_at.isoformat() if n.created_at else None,
    )


async def _own_company(db: AsyncSession, account: Account) -> Company | None:
    return await db.scalar(select(Company).where(Company.account_id == account.id))


@router.get("/company", response_model=CompanyOut | None)
async def get_company(
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> CompanyOut | None:
    company = await _own_company(db, account)
    return _company_out(company) if company else None


@router.put("/company", response_model=CompanyOut, dependencies=[Depends(require_csrf)])
async def upsert_company(
    payload: CompanyIn,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> CompanyOut:
    """FR-16: профиль компании; один аккаунт — одна компания (MVP)."""
    company = await _own_company(db, account)
    if company is None:
        company = Company(account_id=account.id)
        db.add(company)

    if payload.industry_id is not None:
        industry = await db.get(Industry, payload.industry_id)
        if industry is None:
            raise errors.Problem(422, errors.VALIDATION_FAILED, errors.E04_REFERENCE, "Неизвестная отрасль",
                                 errors=[{"field": "industry_id", "code": "REFERENCE_INVALID", "error_class": "E04", "message": "Отрасль отсутствует в справочнике"}],
                                 recovery="correct_input")

    if company.version != payload.version:
        raise errors.Problem(409, "VERSION_CONFLICT", errors.E11_CONCURRENCY, "Компания изменена в другой вкладке",
                             detail="Обновите страницу и повторите сохранение.", recovery="refresh")

    company.name = payload.name
    company.industry_id = payload.industry_id
    company.description = payload.description
    company.contact_email = payload.contact_email
    company.website = payload.website
    company.phone = payload.phone
    company.version += 1
    await db.commit()
    await db.refresh(company)
    return _company_out(company)


@router.get("/needs", response_model=list[EmployerNeedOut])
async def list_needs(
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> list[EmployerNeedOut]:
    company = await _own_company(db, account)
    if company is None:
        return []
    needs = (await db.scalars(select(EmployerNeed).where(EmployerNeed.company_id == company.id).order_by(EmployerNeed.created_at.desc()))).all()
    return [_need_out(n) for n in needs]


@router.post("/needs", response_model=EmployerNeedOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_need(
    payload: EmployerNeedIn,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> EmployerNeedOut:
    """FR-17: рабочая потребность (внутренний объект, не вакансия)."""
    company = await _own_company(db, account)
    if company is None:
        raise errors.Problem(409, errors.INVALID_STATE, errors.E12_STATE,
                             "Сначала заполните профиль компании",
                             detail="Потребности можно создавать после сохранения компании.", recovery="correct_input")
    if company.contact_email is None or not company.name:
        raise errors.Problem(409, "INVALID_STATE", errors.E12_STATE, "Профиль компании неполный",
                             detail="Укажите название и контактный email компании.", recovery="correct_input")

    grade_ids = set(payload.grade_ids)
    skill_ids = set(payload.skill_ids)
    if len(set((await db.scalars(select(Grade.id).where(Grade.id.in_(grade_ids)))).all())) != len(grade_ids):
        raise errors.Problem(422, errors.VALIDATION_FAILED, errors.E04_REFERENCE, "Неизвестный грейд",
                             errors=[{"field": "grade_ids", "code": "REFERENCE_INVALID", "error_class": "E04", "message": "Грейд отсутствует в справочнике"}], recovery="correct_input")
    if len(set((await db.scalars(select(Skill.id).where(Skill.id.in_(skill_ids)))).all())) != len(skill_ids):
        raise errors.Problem(422, errors.VALIDATION_FAILED, errors.E04_REFERENCE, "Неизвестный навык",
                             errors=[{"field": "skill_ids", "code": "REFERENCE_INVALID", "error_class": "E04", "message": "Навык отсутствует в справочнике"}], recovery="correct_input")
    if payload.specialization_id is not None:
        if await db.get(Specialization, payload.specialization_id) is None:
            raise errors.Problem(422, errors.VALIDATION_FAILED, errors.E04_REFERENCE, "Неизвестная специализация",
                                 errors=[{"field": "specialization_id", "code": "REFERENCE_INVALID", "error_class": "E04", "message": "Специализация отсутствует в справочнике"}], recovery="correct_input")

    need = EmployerNeed(
        company_id=company.id,
        title=payload.title,
        tasks_text=payload.tasks_text,
        industry_id=payload.industry_id,
        specialization_id=payload.specialization_id,
        grades=[g for g in (await db.scalars(select(Grade).where(Grade.id.in_(grade_ids)))).all()],
        skills=[s for s in (await db.scalars(select(Skill).where(Skill.id.in_(skill_ids)))).all()],
    )
    db.add(need)
    await db.commit()
    await db.refresh(need)
    return _need_out(need)


@router.get("/needs/{need_id}", response_model=EmployerNeedOut)
async def get_need(
    need_id: uuid.UUID,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> EmployerNeedOut:
    """E09: чужой объект не раскрывается (единый 404)."""
    need = await db.get(EmployerNeed, need_id)
    company = await _own_company(db, account)
    if need is None or company is None or need.company_id != company.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS, "Потребность не найдена", recovery="none")
    return _need_out(need)


@router.put("/needs/{need_id}", response_model=EmployerNeedOut, dependencies=[Depends(require_csrf)])
async def update_need(
    need_id: uuid.UUID,
    payload: EmployerNeedIn,
    account: Account = EmployerDep,
    db: AsyncSession = Depends(get_db),
) -> EmployerNeedOut:
    """FR-17: изменение потребности меняет подбор, но не переписывает отправленные предложения."""
    need = await db.get(EmployerNeed, need_id)
    company = await _own_company(db, account)
    if need is None or company is None or need.company_id != company.id:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS, "Потребность не найдена", recovery="none")
    grade_ids = set(payload.grade_ids)
    skill_ids = set(payload.skill_ids)
    need.title = payload.title
    need.tasks_text = payload.tasks_text
    need.industry_id = payload.industry_id
    need.specialization_id = payload.specialization_id
    need.grades = [g for g in (await db.scalars(select(Grade).where(Grade.id.in_(grade_ids)))).all()]
    need.skills = [s for s in (await db.scalars(select(Skill).where(Skill.id.in_(skill_ids)))).all()]
    await db.commit()
    await db.refresh(need)
    return _need_out(need)