"""Проверки Этапа 3 «Подбор» против живого сервера.

Покрывает:
- исключение неподходящих специализаций и грейдов;
- формулу балла 60% компетенции + 30% тест + 10% ФСП (с объяснениями);
- фильтры по грейду и минимальному баллу;
- пагинацию.

Скрипт создаёт собственных кандидатов и тестовую потребность (детерминированные
данные, не зависящие от демо-наполнения). Запуск (в контейнере API):
    docker compose exec -T api python scripts/verify_stage3.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

import httpx

from sqlalchemy import select

PASSWORD = "DemoPass2026!"
EMPLOYER_EMAIL = "employer@example.com"

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _csrf(c: httpx.AsyncClient) -> str:
    return c.cookies.get("fsp_csrf") or ""


async def setup_data() -> dict:
    """Создаёт кандидатов A-D и тестовую потребность (python backend, junior)."""
    from app.core.security import hash_password
    from app.db.base import async_session_factory
    from app.models.account import Account, AccountStatus, Role
    from app.models.assessment import ConfirmedCategory, TestAttempt, TestAttemptStatus
    from app.models.candidate import CandidateProfile
    from app.models.employer import Company, EmployerNeed
    from app.models.reference import Grade, Skill, Specialization

    now = datetime.now(UTC)
    async with async_session_factory() as s:
        # Очистка собственных данных предыдущих прогонов (этапы 2 и 3)
        from sqlalchemy import delete

        await s.execute(delete(Account).where(Account.email_normalized.like("stage2-%")))
        await s.execute(delete(Account).where(Account.email_normalized.like("match-%")))
        await s.execute(delete(EmployerNeed).where(EmployerNeed.title.like("Этап3:%")))

        refs: dict = {}
        specs = {x.code: x for x in (await s.scalars(select(Specialization))).all()}
        grades = {g.code: g for g in (await s.scalars(select(Grade))).all()}
        skills = {sk.code: sk for sk in (await s.scalars(select(Skill))).all()}

        async def make_candidate(
            tag: str,
            spec_code: str,
            grade_code: str,
            skill_codes: list[str],
            test_score: int | None,
            fsp: bool = False,
        ) -> str:
            email = f"match-{tag}-{uuid.uuid4().hex[:6]}@example.com"
            acc = Account(
                email=email, email_normalized=email, password_hash=hash_password(PASSWORD),
                role=Role.CANDIDATE, status=AccountStatus.ACTIVE,
                consent_version="1.0", consent_granted_at=now, confirmed_at=now,
            )
            s.add(acc)
            await s.flush()
            profile = CandidateProfile(
                account_id=acc.id, full_name=f"Кандидат {tag.upper()}", phone=None,
                experience_months=24, claimed_level_id=None, soft_skills=[],
                about="Контрольный профиль этапа 3.", is_published=True,
                show_fsp=fsp, fsp_member_id="FSP-0001" if fsp else None,
            )
            profile.skills = [skills[c] for c in skill_codes]
            s.add(profile)
            await s.flush()
            cat = ConfirmedCategory(
                candidate_id=profile.id, specialization_id=specs[spec_code].id,
                grade_id=grades[grade_code].id, is_active=True,
            )
            s.add(cat)
            await s.flush()
            if test_score is not None:
                attempt = TestAttempt(
                    candidate_id=profile.id, specialization_id=specs[spec_code].id,
                    grade_level=grades[grade_code].level, status=TestAttemptStatus.COMPLETED,
                    started_at=now - timedelta(hours=1), expires_at=now - timedelta(minutes=30),
                    submitted_at=now - timedelta(hours=1),
                    correct_count=round(test_score / 100 * 6), total_count=6,
                    score_percent=test_score,
                    result_grade_id=grades[grade_code].id,
                )
                s.add(attempt)
            return email

        refs["A"] = await make_candidate("a", "python_backend", "junior", ["python", "fastapi", "sql"], 100)
        refs["B"] = await make_candidate("b", "python_backend", "junior", ["python", "fastapi"], 70)
        refs["C"] = await make_candidate("c", "python_backend", "middle", ["python", "fastapi", "sql"], 100, fsp=True)
        refs["D"] = await make_candidate("d", "system_analysis", "junior", ["requirements"], 100)

        # тестовая потребность: только junior -> средний грейд исключается
        acc = await s.scalar(select(Account).where(Account.email_normalized == EMPLOYER_EMAIL))
        company = await s.scalar(select(Company).where(Company.account_id == acc.id))
        need = EmployerNeed(
            company_id=company.id,
            title="Этап3: Python Junior (контроль)",
            tasks_text="Контрольная потребность для проверки подбора этапа 3. Проверка формулы, фильтров и пагинации.",
            specialization_id=specs["python_backend"].id,
            grades=[grades["junior"]],
            skills=[skills["python"], skills["fastapi"], skills["sql"]],
        )
        s.add(need)
        await s.commit()
        await s.refresh(need)
        refs["need_id"] = str(need.id)
        return refs


async def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "OK " if cond else "FAIL"
        print(f"[{status}] {name} {extra}")
        if not cond:
            failures.append(name)

    base = os.environ.get("SMOKE_BASE", "http://localhost:8000") + "/api/v1"
    data = await setup_data()
    need_id = data["need_id"]

    async with httpx.AsyncClient(base_url=base, timeout=15.0) as emp:
        r = await emp.post("/auth/login", json={"email": EMPLOYER_EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            print(f"Вход работодателя не удался: {r.status_code} {r.text[:300]}")
            return 1

        url = f"/employer/needs/{need_id}/matches"

        # --- полная выдача: исключены D (специализация) и C (грейд) ---
        r = await emp.get(f"{url}?page=1&page_size=10")
        check("подбор 200", r.status_code == 200, str(r.status_code))
        page = r.json()
        items = page["items"]
        names = [i["full_name"] for i in items]
        check("исключены неподходящие специализация и грейд",
              page["total"] == 2 and "Кандидат D" not in names and "Кандидат C" not in names,
              f"total={page['total']}")

        by_name = {i["full_name"]: i for i in items}
        a = by_name.get("Кандидат A")
        b = by_name.get("Кандидат B")
        check("кандидат A: 60(навыки) + 30(тест 100%) + 0 = 90",
              a is not None and a["score"] == 90
              and a["score_breakdown"] == {"competencies": 60.0, "test": 30.0, "fsp": 0.0},
              f"score={a and a['score']}")
        check("кандидат B: 40(2/3 навыков) + 21(70%) + 0 = 61",
              b is not None and b["score"] == 61
              and b["score_breakdown"] == {"competencies": 40.0, "test": 21.0, "fsp": 0.0},
              f"score={b and b['score']}")
        check("сортировка по баллу", items[0]["full_name"] == "Кандидат A",
              items[0]["full_name"] if items else "-")
        check("объяснения включают компетенции, тест и ФСП",
              all(any("Компетенции" in rr for rr in i["reasons"])
                  and any("Результат теста" in rr for rr in i["reasons"])
                  and any("ФСП" in rr for rr in i["reasons"]) for i in items))

        # --- фильтры ---
        r = await emp.get(f"{url}?grade=middle")
        check("фильтр grade=middle — пусто", r.json()["total"] == 0, str(r.json()["total"]))
        r = await emp.get(f"{url}?min_score=70")
        check("фильтр min_score=70 — только A", r.json()["total"] == 1
              and r.json()["items"][0]["full_name"] == "Кандидат A", str(r.json()["total"]))
        r = await emp.get(f"{url}?grade=junior&min_score=61")
        check("фильтры вместе — A и B", r.json()["total"] == 2, str(r.json()["total"]))

        # --- пагинация ---
        r = await emp.get(f"{url}?page=1&page_size=1")
        p1 = r.json()
        r = await emp.get(f"{url}?page=2&page_size=1")
        p2 = r.json()
        check("пагинация page_size=1: 2 страницы",
              p1["pages"] == 2 and p1["total"] == 2 and len(p1["items"]) == 1 and len(p2["items"]) == 1
              and p1["items"][0]["candidate_id"] != p2["items"][0]["candidate_id"],
              f"pages={p1['pages']}, page2_len={len(p2['items'])}")
        r = await emp.get(f"{url}?page=99&page_size=10")
        check("страница за пределами — пустой items", r.json()["items"] == [], str(r.json()["total"]))

    if failures:
        print(f"\nПровалено проверок: {len(failures)}: {failures}")
        return 1
    print("\nЭтап 3 (подбор): все проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))