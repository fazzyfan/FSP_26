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

        # --- 2. Сводка оценки: 4 категории (2 специализации × 2 грейда) ---
        r = await cand.get("/candidate/assessment")
        check("сводка оценки", r.status_code == 200, str(r.status_code))
        summary = r.json()
        tests = {t["specialization_name"]: t for t in summary["tests"]}
        spec = tests.get("Python backend")
        check("тест Python backend: 12 заданий, 2 грейда",
              spec is not None and spec["questions_count"] == 12 and len(spec["grades"]) == 2,
              str(spec) if spec else "нет")
        if spec is None:
            print("\nПровалено: нет вопросов по специализации Python backend")
            return 1

        # --- 3. Старт попытки выбранной категории → ответы → восстановление → отправка ---
        grade_code = summary["category"]["grade_code"] if summary.get("category") else "junior"
        r = await cand.post(
            f"/candidate/assessment/tests/{spec['specialization_id']}/start",
            headers={"X-CSRF-Token": _csrf(cand)},
            json={"grade": grade_code},
        )
        if r.status_code == 201:
            st = r.json()
            attempt_id = st["attempt_id"]
            check("старт попытки", True, f"{grade_code} {attempt_id}")
            qs = st["questions"]
            check("6 заданий в 3 блоках",
                  len(qs) == 6 and sorted({q["block"] for q in qs}) == [1, 2, 3],
                  f"{len(qs)} заданий")
            check("таймер 20 минут задан", st["remaining_seconds"] > 0 and st["remaining_seconds"] <= 20 * 60,
                  f"{st['remaining_seconds']} c")

            # правильные ответы сохраняются по мере выбора
            correct = await correct_answers()
            answers = [
                {"question_id": q["id"], "option_id": correct[q["id"]]}
                for q in qs if q["id"] in correct
            ]
            r = await cand.put(
                f"/candidate/assessment/attempts/{attempt_id}/answers",
                headers={"X-CSRF-Token": _csrf(cand)},
                json={"answers": answers},
            )
            check("сохранение ответов", r.status_code == 200 and len(r.json()["answers"]) == 6, str(r.status_code))

            # восстановление после перезагрузки страницы
            r = await cand.get(f"/candidate/assessment/attempts/{attempt_id}")
            restored = r.status_code == 200 and len(r.json()["answers"]) == 6 and r.json()["remaining_seconds"] > 0
            check("восстановление попытки", restored, str(r.status_code))

            # отправка: суммарно 100%, каждый блок 2/2
            r = await cand.post(
                f"/candidate/assessment/attempts/{attempt_id}/submit",
                headers={"X-CSRF-Token": _csrf(cand)},
            )
            check("отправка теста", r.status_code == 200 and r.json()["passed"] is True,
                  f"score={r.json().get('score_percent')}%")
            if r.status_code == 200:
                result = r.json()
                check("все блоки пройдены",
                      all(b["correct"] == b["total"] and b["total"] == 2 for b in result["block_results"]),
                      str(result["block_results"]))
                check("категория подтверждена", result["grade_code"] == grade_code,
                      f"grade={result['grade_code']}")

            # защита от повторной отправки и перезаписи
            r2 = await cand.post(
                f"/candidate/assessment/attempts/{attempt_id}/submit",
                headers={"X-CSRF-Token": _csrf(cand)},
            )
            check("повторная отправка 409", r2.status_code == 409, str(r2.status_code))
            r2 = await cand.put(
                f"/candidate/assessment/attempts/{attempt_id}/answers",
                headers={"X-CSRF-Token": _csrf(cand)},
                json={"answers": answers},
            )
            check("перезапись завершённой попытки 409", r2.status_code == 409, str(r2.status_code))
        elif r.status_code == 409:
            # кулдаун (24 ч для той же категории) или 90 дней для смены — повторный прогон
            check("кулдаун теста (повторный прогон)",
                  summary["category"] is not None or summary["last_attempt"] is not None,
                  r.json().get("detail", ""))
        else:
            check("старт попытки", False, f"{r.status_code} {r.text[:300]}")

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

        r = await emp.get(f"/employer/needs/{need['id']}/matches?page=1&page_size=10")
        check("подбор кандидатов", r.status_code == 200, str(r.status_code))
        page_data = r.json()
        matches = page_data["items"]
        check("в подборе есть кандидаты", len(matches) > 0 and page_data["total"] > 0,
              f"total={page_data['total']}")
        # Предпочитаем демо-кандидата (имя может быть изменено smoke-тестом),
        # исключая контрольных кандидатов из скриптов этапов
        match = next(
            (m for m in matches if not m["full_name"].startswith(("Кандидат ", "Этап2 "))),
            None,
        )
        if match is None:
            match = max(matches, key=lambda m: m["score"]) if matches else None
        if match:
            check("кандидат с ненулевым баллом", match["score"] > 0, f"score={match['score']}")
            bd = match["score_breakdown"]
            check("разбивка балла 60/30/10",
                  round(bd["competencies"] + bd["test"] + bd["fsp"]) == match["score"],
                  f"60/30/10 -> {match['score']}")
            check("объяснение подбора", len(match["reasons"]) >= 2, "; ".join(match["reasons"][:2]))

        # --- 6. Приглашение (обязательные условия; повторы не создают дублей) ---
        invitation_id: str | None = None
        if match:
            payload = {
                "candidate_id": match["candidate_id"],
                "salary_from": 120_000,
                "salary_to": 180_000,
                "message": "Демо-приглашение из цепочки проверки.",
            }
            r = await emp.post(
                f"/employer/needs/{need['id']}/invitations",
                headers={"X-CSRF-Token": _csrf(emp)},
                json=payload,
            )
            if r.status_code in (200, 201):
                invitation_id = r.json()["id"]
                check("создание приглашения", True, f"http={r.status_code} {invitation_id}")
                # идемпотентный повтор с теми же условиями -> 200 и тот же id
                r2 = await emp.post(
                    f"/employer/needs/{need['id']}/invitations",
                    headers={"X-CSRF-Token": _csrf(emp)},
                    json=payload,
                )
                check("повтор не создаёт дубль",
                      r2.status_code in (200, 201) and r2.json().get("id") == invitation_id,
                      f"http={r2.status_code}")
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

        # --- 8. Контакты открыты только после принятия; отзыв доступа (FR-27) ---
        if invitation_id:
            r = await emp.get(f"/employer/invitations/{invitation_id}/contacts")
            if r.status_code == 200:
                check("контакты открыты после принятия",
                      r.json().get("email") == CANDIDATE_EMAIL,
                      r.json().get("email", ""))
                # Отзыв доступа кандидатом
                r = await cand.post(
                    f"/candidate/invitations/{invitation_id}/contacts/revoke",
                    headers={"X-CSRF-Token": _csrf(cand)},
                )
                check("отзыв доступа к контактам",
                      r.status_code == 200 and r.json().get("contacts_revoked_at") is not None,
                      str(r.status_code))
                r = await emp.get(f"/employer/invitations/{invitation_id}/contacts")
                check("контакты закрыты после отзыва", r.status_code == 409, str(r.status_code))
                # Повтор старого принятия не восстанавливает доступ
                r = await cand.post(
                    f"/candidate/invitations/{invitation_id}/respond",
                    headers={"X-CSRF-Token": _csrf(cand)},
                    json={"decision": "accept"},
                )
                check("повторный accept идемпотентен",
                      r.status_code == 200 and r.json().get("contacts_revoked_at") is not None,
                      str(r.status_code))
                r = await emp.get(f"/employer/invitations/{invitation_id}/contacts")
                check("доступ не восстановлен после повтора", r.status_code == 409, str(r.status_code))
            else:
                check("контакты закрыты (прошлые прогоны: отзыв/отклонение)",
                      r.status_code == 409, str(r.status_code))

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