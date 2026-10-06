"""Сквозная проверка полного пути (этап 2):

    Профиль → тест → категория → подбор → приглашение → принятие → контакты

Запуск внутри контейнера API (миграции и seed уже применены):
    docker compose exec -T api python scripts/chain_check.py

Проверка против живого сервера снаружи (без доступа к БД не сработает поиск
правильных ответов — используйте запуск в контейнере):
    set SMOKE_BASE=http://localhost:8000
    docker compose exec -T api python scripts/chain_check.py

Скрипт идемпотентен: повторные прогоны переживают кулдаун теста (24 ч после
неуспеха, 90 дней после успеха) и дубль приглашения по паре (need, candidate).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import httpx

PASSWORD = "DemoPass2026!"
CANDIDATE_EMAIL = "candidate@example.com"
EMPLOYER_EMAIL = "employer@example.com"

# Скрипт запускается из подкаталога scripts/ — нужен корень проекта для импорта app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Консоль Windows (cp1252) не выводит кириллицу — переключаемся на UTF-8
if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _csrf(c: httpx.AsyncClient) -> str:
    return c.cookies.get("fsp_csrf") or ""


async def _login(c: httpx.AsyncClient, email: str) -> None:
    r = await c.post("/auth/login", json={"email": email, "password": PASSWORD})
    if r.status_code != 200:
        raise SystemExit(f"Вход {email}: {r.status_code} {r.text[:300]}")


async def correct_answers() -> dict[str, str]:
    """question_id -> option_id правильного ответа (доступ к БД внутри контейнера)."""
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.models.assessment import TestQuestionOption

    async with async_session_factory() as session:
        rows = (await session.execute(select(TestQuestionOption.question_id, TestQuestionOption.id)
                                      .where(TestQuestionOption.is_correct.is_(True)))).all()
        return {str(q): str(o) for q, o in rows}


async def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "OK " if cond else "FAIL"
        print(f"[{status}] {name} {extra}")
        if not cond:
            failures.append(name)

    base = os.environ.get("SMOKE_BASE", "http://localhost:8000") + "/api/v1"

    async with httpx.AsyncClient(base_url=base, timeout=15.0) as cand, \
               httpx.AsyncClient(base_url=base, timeout=15.0) as emp:
        # --- 1. Кандидат: вход, профиль есть ---
        await _login(cand, CANDIDATE_EMAIL)
        r = await cand.get("/candidate/profile")
        check("профиль кандидата заполнен", r.status_code == 200 and r.json() is not None, str(r.status_code))
        if r.json() is None:
            print("  >> Сначала заполните профиль кандидата (seed делает это автоматически)")

        # --- 2. Сводка оценки ---
        r = await cand.get("/candidate/assessment")
        check("сводка оценки", r.status_code == 200, str(r.status_code))
        summary = r.json()
        tests = {t["specialization_name"]: t for t in summary["tests"]}
        spec = tests.get("Python backend")
        check("доступен тест Python backend", spec is not None and spec["questions_count"] == 6,
              str(spec) if spec else "нет")
        if spec is None:
            print("\nПровалено: нет вопросов по специализации Python backend")
            return 1

        # --- 3. Вопросы + отправка ответов (если ещё нет категории/кулдауна) ---
        r = await cand.get(f"/candidate/assessment/tests/{spec['specialization_id']}/questions")
        check("получение вопросов", r.status_code == 200 and len(r.json()) == 6, str(r.status_code))
        questions = r.json()

        need_submit = summary["category"] is None
        if summary["next_attempt_at"]:
            need_submit = False  # кулдаун после предыдущей попытки

        if need_submit:
            correct = await correct_answers()
            answers = [
                {"question_id": q["id"], "option_id": correct[q["id"]]}
                for q in questions if q["id"] in correct
            ]
            r = await cand.post(
                f"/candidate/assessment/tests/{spec['specialization_id']}/submit",
                headers={"X-CSRF-Token": _csrf(cand)},
                json={"answers": answers},
            )
            if r.status_code == 409:
                # кулдаун — перечитаем сводку
                r = await cand.get("/candidate/assessment")
                summary = r.json()
                check("кулдаун теста (повторный прогон)",
                      summary["category"] is not None and summary["last_attempt"] is not None,
                      summary.get("next_attempt_at") or "")
            else:
                check("отправка теста", r.status_code == 200, str(r.status_code))
                if r.status_code == 200:
                    result = r.json()
                    check("тест пройден", result["passed"] is True, f"score={result['score_percent']}%")
                    check("категория подтверждена", result["grade_code"] in ("junior", "middle"),
                          f"grade={result['grade_code']}")

        # --- 4. Категория в сводке ---
        r = await cand.get("/candidate/assessment")
        summary = r.json()
        check("подтверждённая категория есть", summary["category"] is not None,
              str(summary["category"]) if summary["category"] else "нет")
        if summary["category"] is None:
            print("\nПровалено: категория не подтверждена — дальше цепочка невозможна")
            return 1

        # --- 5. Работодатель: потребность и подбор ---
        await _login(emp, EMPLOYER_EMAIL)
        r = await emp.get("/employer/needs")
        check("список потребностей", r.status_code == 200 and len(r.json()) > 0, str(r.status_code))
        needs = r.json()
        need = next((n for n in needs if n["title"] == "Backend-разработчик (Python)"), needs[0])

        r = await emp.get(f"/employer/needs/{need['id']}/matches")
        check("подбор кандидатов", r.status_code == 200, str(r.status_code))
        matches = r.json()
        check("в подборе есть кандидаты", len(matches) > 0, f"{len(matches)} совпадений")
        match = max(matches, key=lambda m: m["score"]) if matches else None
        if match:
            check("кандидат с ненулевым баллом", match["score"] > 0, f"score={match['score']}")
            check("объяснение подбора", len(match["reasons"]) >= 2, "; ".join(match["reasons"][:2]))

        # --- 6. Приглашение ---
        invitation_id: str | None = None
        if match:
            r = await emp.post(
                f"/employer/needs/{need['id']}/invitations",
                headers={"X-CSRF-Token": _csrf(emp)},
                json={
                    "candidate_id": match["candidate_id"],
                    "salary_from": 120_000,
                    "salary_to": 180_000,
                    "message": "Демо-приглашение из цепочки проверки.",
                },
            )
            if r.status_code == 201:
                invitation_id = r.json()["id"]
                check("создание приглашения", True, str(invitation_id))
            elif r.status_code == 409:
                invites = (await emp.get("/employer/invitations")).json()
                pending = [i for i in invites if i["status"] in ("pending", "accepted")]
                invitation_id = pending[0]["id"] if pending else None
                check("приглашение уже существует (повторный прогон)", invitation_id is not None,
                      " / ".join(i["status"] for i in invites))
            else:
                check("создание приглашения", False, f"{r.status_code} {r.text[:300]}")

        # --- 7. Кандидат: принять приглашение ---
        if invitation_id:
            r = await cand.get("/candidate/invitations")
            invites = r.json()
            inv = next((i for i in invites if i["id"] == invitation_id), None)
            check("приглашение видно кандидату", inv is not None, str(invitation_id))
            if inv and inv["status"] == "pending":
                r = await cand.post(
                    f"/candidate/invitations/{invitation_id}/respond",
                    headers={"X-CSRF-Token": _csrf(cand)},
                    json={"decision": "accept"},
                )
                check("принятие приглашения", r.status_code == 200 and r.json()["status"] == "accepted",
                      str(r.status_code))

        # --- 8. Работодатель: контакты открыты только после принятия ---
        if invitation_id:
            r = await emp.get(f"/employer/invitations/{invitation_id}/contacts")
            check("контакты открыты после принятия",
                  r.status_code == 200 and r.json().get("email") == CANDIDATE_EMAIL,
                  f"{r.status_code} {r.text[:200] if r.status_code != 200 else r.json().get('email', '')}")

        # --- 9. Права: контакты недоступны без принятия ---
        invites = (await emp.get("/employer/invitations")).json()
        declined = [i for i in invites if i["status"] == "declined"]
        withdrawn = [i for i in invites if i["status"] == "withdrawn"]
        blocked = declined + withdrawn
        if blocked:
            r = await emp.get(f"/employer/invitations/{blocked[0]['id']}/contacts")
            check("контакты закрыты для отклонённых", r.status_code == 409, str(r.status_code))

    if failures:
        print(f"\nПровалено проверок: {len(failures)}: {failures}")
        return 1
    print("\nПолный путь прошёл: профиль → тест → категория → подбор → приглашение → принятие → контакты.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))