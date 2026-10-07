"""Проверки Этапа 4 «ФСП, PDF, согласия, права» против живого сервера.

Покрывает:
- PDF собственного профиля кандидата (200, application/pdf);
- PDF для работодателя: 409 без доступа, 200 с доступом, 409 после отзыва;
- демо-адаптер ФСП: достижения при включённом показе;
- отзыв согласий: публикация, показ ФСП, обработка данных (эффекты на сервере);
- доступ к чужим объектам: 404 для обеих ролей.

Запуск (в контейнере API):
    docker compose exec -T api python scripts/verify_stage4.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime

import httpx

from sqlalchemy import select

PASSWORD = "DemoPass2026!"

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _csrf(c: httpx.AsyncClient) -> str:
    return c.cookies.get("fsp_csrf") or ""


async def create_candidate() -> tuple[str, str]:
    """Создаёт кандидата с публикацией, ФСП и категорией; возвращает (email, profile_id)."""
    from app.core.security import hash_password
    from app.db.base import async_session_factory
    from app.models.account import Account, AccountStatus, Role
    from app.models.assessment import ConfirmedCategory
    from app.models.candidate import CandidateProfile
    from app.models.reference import Grade, Specialization

    email = f"stage4-{uuid.uuid4().hex[:8]}@example.com"
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        spec = await session.scalar(select(Specialization).where(Specialization.code == "python_backend"))
        grade = await session.scalar(select(Grade).where(Grade.code == "junior"))
        acc = Account(
            email=email, email_normalized=email, password_hash=hash_password(PASSWORD),
            role=Role.CANDIDATE, status=AccountStatus.ACTIVE,
            consent_version="1.0", consent_granted_at=now, confirmed_at=now,
        )
        session.add(acc)
        await session.flush()
        profile = CandidateProfile(
            account_id=acc.id, full_name="Кандидат этапа 4", phone="+7 900 111-22-33",
            experience_months=12, claimed_level_id=None, soft_skills=[],
            about="Проверка PDF, согласий и ФСП.", is_published=True,
            show_fsp=True, fsp_member_id="FSP-DEMO-42",
        )
        session.add(profile)
        await session.flush()
        session.add(ConfirmedCategory(
            candidate_id=profile.id, specialization_id=spec.id, grade_id=grade.id, is_active=True,
        ))
        await session.commit()
        await session.refresh(profile)
        return email, str(profile.id)


async def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "OK " if cond else "FAIL"
        print(f"[{status}] {name} {extra}")
        if not cond:
            failures.append(name)

    base = os.environ.get("SMOKE_BASE", "http://localhost:8000") + "/api/v1"
    cand_email, cand_id = await create_candidate()

    async with httpx.AsyncClient(base_url=base, timeout=15.0) as cand, \
               httpx.AsyncClient(base_url=base, timeout=15.0) as emp:
        r = await cand.post("/auth/login", json={"email": cand_email, "password": PASSWORD})
        if r.status_code != 200:
            print(f"Вход кандидата не удался: {r.status_code} {r.text[:300]}")
            return 1
        cand_csrf = _csrf(cand)

        # --- PDF собственного профиля ---
        r = await cand.get("/candidate/profile/pdf")
        check("PDF своего профиля",
              r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf"),
              f"{r.status_code} {r.headers.get('content-type')}")

        # --- Демо-адаптер ФСП ---
        r = await cand.get("/candidate/fsp/achievements")
        data = r.json()
        check("достижения ФСП (демо)",
              r.status_code == 200 and data["visible"] is True and len(data["achievements"]) >= 3,
              f"{len(data.get('achievements', []))} достижений")

        # --- Права: чужие объекты ---
        r = await emp.post("/auth/login", json={"email": "employer@example.com", "password": PASSWORD})
        emp_csrf = _csrf(emp)
        r = await emp.get(f"/employer/invitations/{uuid.UUID(int=1)}/contacts")
        check("контакты чужого id — 404", r.status_code == 404, str(r.status_code))
        r = await emp.get(f"/employer/invitations/{uuid.UUID(int=1)}/profile-pdf")
        check("PDF по чужому id — 404", r.status_code == 404, str(r.status_code))

        # --- Приглашение и PDF для работодателя (разрешение проверяется в PDF) ---
        needs = (await emp.get("/employer/needs")).json()
        need = needs[0]
        r = await emp.post(
            f"/employer/needs/{need['id']}/invitations",
            headers={"X-CSRF-Token": emp_csrf},
            json={"candidate_id": cand_id, "salary_from": 100_000, "salary_to": 150_000,
                  "message": "Приглашение для проверки PDF работодателя."},
        )
        check("приглашение создано", r.status_code in (200, 201), f"http={r.status_code} {r.text[:120]}")
        inv_id = r.json()["id"]

        r = await emp.get(f"/employer/invitations/{inv_id}/profile-pdf")
        check("PDF до принятия — 409", r.status_code == 409, str(r.status_code))

        r = await cand.post(f"/candidate/invitations/{inv_id}/respond",
                            headers={"X-CSRF-Token": cand_csrf}, json={"decision": "accept"})
        check("принятие приглашения", r.status_code == 200, str(r.status_code))
        r = await emp.get(f"/employer/invitations/{inv_id}/profile-pdf")
        check("PDF после принятия — 200",
              r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf"),
              str(r.status_code))

        r = await cand.post(f"/candidate/invitations/{inv_id}/contacts/revoke",
                            headers={"X-CSRF-Token": cand_csrf})
        check("отзыв доступа к контактам", r.status_code == 200, str(r.status_code))
        r = await emp.get(f"/employer/invitations/{inv_id}/profile-pdf")
        check("PDF после отзыва — 409", r.status_code == 409, str(r.status_code))

        # --- Согласия (FR-04) ---
        r = await cand.get("/candidate/consents")
        consents = r.json()["consents"]
        codes = {c["code"] for c in consents}
        check("три типа согласий",
              r.status_code == 200 and {"data_processing", "profile_publication", "fsp_showcase"} <= codes,
              str(sorted(codes)))

        r = await cand.post("/candidate/consents/revoke", headers={"X-CSRF-Token": cand_csrf},
                            json={"code": "profile_publication"})
        revoked = next(c for c in r.json()["consents"] if c["code"] == "profile_publication")
        check("отзыв публикации", r.status_code == 200 and revoked["granted"] is False, str(r.status_code))
        profile = (await cand.get("/candidate/profile")).json()
        check("профиль скрыт из подбора", profile["is_published"] is False)

        r = await cand.post("/candidate/consents/revoke", headers={"X-CSRF-Token": cand_csrf},
                            json={"code": "fsp_showcase"})
        r2 = await cand.get("/candidate/fsp/achievements")
        check("отзыв показа ФСП", r.status_code == 200 and r2.json()["visible"] is False, str(r.status_code))

        r = await cand.post("/candidate/consents/revoke", headers={"X-CSRF-Token": cand_csrf},
                            json={"code": "data_processing"})
        check("отзыв обработки данных", r.status_code == 200, str(r.status_code))
        r = await cand.get("/candidate/profile")
        check("аккаунт деактивирован — доступ закрыт", r.status_code == 401, str(r.status_code))

    if failures:
        print(f"\nПровалено проверок: {len(failures)}: {failures}")
        return 1
    print("\nЭтап 4 (ФСП, PDF, согласия, права): все проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))