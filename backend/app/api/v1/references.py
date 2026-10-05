"""Справочники для форм (FR-07, FR-16, FR-17) и тексты согласий (FR-01)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.account import ConsentDoc
from app.models.reference import Grade, Industry, RoleRef, Skill, Specialization
from app.schemas.reference import ConsentDocOut, ReferenceItem

router = APIRouter(prefix="/references", tags=["references"])


@router.get("/industries", response_model=list[ReferenceItem])
async def industries(db: AsyncSession = Depends(get_db)) -> list[ReferenceItem]:
    return list((await db.scalars(select(Industry).order_by(Industry.name))).all())


@router.get("/specializations", response_model=list[ReferenceItem])
async def specializations(db: AsyncSession = Depends(get_db)) -> list[ReferenceItem]:
    return list((await db.scalars(select(Specialization).order_by(Specialization.name))).all())


@router.get("/grades", response_model=list[ReferenceItem])
async def grades(db: AsyncSession = Depends(get_db)) -> list[ReferenceItem]:
    return list((await db.scalars(select(Grade).order_by(Grade.level))).all())


@router.get("/skills", response_model=list[ReferenceItem])
async def skills(db: AsyncSession = Depends(get_db)) -> list[ReferenceItem]:
    return list((await db.scalars(select(Skill).order_by(Skill.name))).all())


@router.get("/roles", response_model=list[ReferenceItem])
async def roles(db: AsyncSession = Depends(get_db)) -> list[ReferenceItem]:
    return list((await db.scalars(select(RoleRef).order_by(RoleRef.name))).all())


@router.get("/consents", response_model=list[ConsentDocOut])
async def consents(db: AsyncSession = Depends(get_db)) -> list[ConsentDocOut]:
    return list((await db.scalars(select(ConsentDoc).order_by(ConsentDoc.code, ConsentDoc.effective_at.desc()))).all())