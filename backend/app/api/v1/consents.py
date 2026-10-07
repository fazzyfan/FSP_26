"""Управление согласиями и публикацией (FR-01, FR-04).

Отзыв согласия фиксируется в ConsentEvent; применяются эффекты:
- profile_publication — профиль скрывается из подбора (is_published=False);
- fsp_showcase — показ достижений ФСП отключается (show_fsp=False);
- data_processing — аккаунт деактивируется (статус DEACTIVATED).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_csrf, require_roles
from app.core import errors
from app.db.base import get_db
from app.models.account import Account, AccountStatus, ConsentDoc, ConsentEvent, ConsentType, Role
from app.models.candidate import CandidateProfile

router = APIRouter(tags=["consents"])

CandidateDep = Depends(require_roles(Role.CANDIDATE))

REVOKE_EFFECTS: dict[ConsentType, str] = {
    ConsentType.PROFILE_PUBLICATION: "Профиль скрыт из подбора.",
    ConsentType.FSP_SHOWCASE: "Показ достижений ФСП отключён.",
    ConsentType.DATA_PROCESSING: "Аккаунт деактивирован: вход и обработка данных прекращены.",
}


class ConsentStateOut(BaseModel):
    code: str
    version: str
    title: str
    granted: bool
    effect: str | None = None


class ConsentsOut(BaseModel):
    consents: list[ConsentStateOut]


class RevokeIn(BaseModel):
    code: str


@router.get("/candidate/consents", response_model=ConsentsOut)
async def list_consents(
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> ConsentsOut:
    """Текущие согласия кандидата с историей отзывов."""
    docs = (await db.scalars(select(ConsentDoc).order_by(ConsentDoc.code))).all()
    events = (
        await db.scalars(
            select(ConsentEvent)
            .where(ConsentEvent.account_id == account.id)
            .order_by(ConsentEvent.created_at.desc())
        )
    ).all()

    revoked_codes = {e.consent_type.value for e in events if not e.granted}
    profile = await db.scalar(select(CandidateProfile).where(CandidateProfile.account_id == account.id))

    items: list[ConsentStateOut] = []
    for doc in docs:
        granted = doc.code not in revoked_codes
        effect = None
        if not granted:
            ctype = ConsentType(doc.code)
            effect = REVOKE_EFFECTS.get(ctype)
        items.append(
            ConsentStateOut(code=doc.code, version=doc.version, title=doc.title, granted=granted, effect=effect)
        )

    # фактическое состояние публикации (синхронизировано с профилем)
    if profile is not None and not profile.is_published:
        for item in items:
            if item.code == ConsentType.PROFILE_PUBLICATION.value:
                item.granted = False
                item.effect = REVOKE_EFFECTS[ConsentType.PROFILE_PUBLICATION]
    return ConsentsOut(consents=items)


@router.post(
    "/candidate/consents/revoke",
    response_model=ConsentsOut,
    dependencies=[Depends(require_csrf)],
)
async def revoke_consent(
    payload: RevokeIn,
    account: Account = CandidateDep,
    db: AsyncSession = Depends(get_db),
) -> ConsentsOut:
    """Отзыв согласия (FR-04): эффект зависит от типа согласия."""
    doc = await db.scalar(select(ConsentDoc).where(ConsentDoc.code == payload.code))
    if doc is None:
        raise errors.Problem(404, errors.RESOURCE_NOT_AVAILABLE, errors.E09_ACCESS,
                             "Согласие не найдено", recovery="none")
    ctype = ConsentType(payload.code)

    already_revoked = await db.scalar(
        select(ConsentEvent).where(
            ConsentEvent.account_id == account.id,
            ConsentEvent.consent_type == ctype,
            ConsentEvent.granted.is_(False),
        )
    )
    if already_revoked is None:
        db.add(
            ConsentEvent(
                account_id=account.id,
                consent_type=ctype,
                version=doc.version,
                granted=False,
            )
        )

    profile = await db.scalar(select(CandidateProfile).where(CandidateProfile.account_id == account.id))
    if ctype == ConsentType.PROFILE_PUBLICATION and profile is not None:
        profile.is_published = False
    elif ctype == ConsentType.FSP_SHOWCASE and profile is not None:
        profile.show_fsp = False
    elif ctype == ConsentType.DATA_PROCESSING:
        account.status = AccountStatus.DEACTIVATED

    await db.commit()
    return await list_consents(account, db)