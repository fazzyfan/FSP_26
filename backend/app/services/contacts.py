"""Разрешение доступа к контактам кандидата (FR-27).

Единая точка проверки: используется в API приглашений и при генерации PDF профиля.

Правило доступа:
- приглашение принято (status == accepted);
- кандидат дал явное согласие (contacts_consented_at не пусто);
- доступ не отозван (contacts_revoked_at пусто).

Повтор старого принятия (идемпотентный respond) не восстанавливает отозванный доступ.
"""

from __future__ import annotations

from app.core import errors
from app.models.invitation import Invitation, InvitationStatus


def contacts_denied_problem(inv: Invitation) -> errors.Problem | None:
    """Возвращает Problem, если доступ к контактам закрыт, иначе None."""
    if inv.status != InvitationStatus.ACCEPTED:
        return errors.Problem(
            409, errors.INVALID_STATE, errors.E12_STATE, "Контакты пока закрыты",
            detail="Контакты кандидата открываются только после принятия приглашения.",
            recovery="none",
        )
    if inv.contacts_consented_at is None:
        return errors.Problem(
            409, errors.INVALID_STATE, errors.E12_STATE, "Контакты пока закрыты",
            detail="Кандидат ещё не дал согласие на открытие контактов.",
            recovery="none",
        )
    if inv.contacts_revoked_at is not None:
        return errors.Problem(
            409, errors.INVALID_STATE, errors.E12_STATE, "Доступ к контактам отозван",
            detail="Кандидат отозвал доступ к контактам этой компании.",
            recovery="none",
        )
    return None


def require_contacts(inv: Invitation) -> None:
    """Поднимает Problem, если доступ к контактам закрыт (FR-27, PDF-профиль)."""
    problem = contacts_denied_problem(inv)
    if problem is not None:
        raise problem